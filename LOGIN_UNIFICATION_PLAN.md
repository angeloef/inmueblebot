# Plan: Unificación del login (landing como único punto de entrada)

> **Estado:** ✅ IMPLEMENTADO (2026-06-10) — código en main. Falta solo setear en
> Render: `VITE_LOGIN_URL` (build del API/dashboard), `NEXT_PUBLIC_DASHBOARD_URL`
> (ya en web/render.yaml) y verificar `PUBLIC_APP_URL`. El usuario anónimo que entra
> al dashboard por bookmark se redirige directo al **/login** de la landing,
> preservando el deep-link (`?next=/dashboard/...`).
> **Fecha:** 2026-06-10
> **Depende de:** `GOOGLE_AUTH_SESSION_PLAN.md` (✅ implementado — Google OAuth ya
> funciona en la API y el dashboard).

> **Cambio vs. plan original:** el handoff y el registration token usan single-use
> vía Redis (`auth_service.mark_jti_used`, fail-closed). El callback de Google con
> email nuevo redirige a `{PUBLIC_APP_URL}/signup/complete?gt=...` (paso 2: nombre
> de inmobiliaria) en vez de auto-crear. Los errores OAuth/handoff vuelven a
> `{PUBLIC_APP_URL}/login?error=...`.

---

## 0. Decisiones tomadas (respuestas del owner, 2026-06-10)

| Decisión | Elección |
|---|---|
| Login canónico | **Landing (viviendapp-web)** — único punto de entrada; el dashboard redirige ahí |
| Dominio | **Seguir en *.onrender.com** (diseño preparado para migrar a dominio custom después) |
| Google signup | **Pedir nombre de inmobiliaria primero** (no más auto-signup silencioso) |
| Tenant de prueba creado con el Google del owner | **Se conserva** como cuenta de test (trial vence solo) |

### Estado actual (el problema)

- **Dos pantallas de login desconectadas**: la landing (`web/`, Next.js BFF en
  `viviendapp-web.onrender.com`) guarda cookies en SU dominio; el dashboard (Vite,
  servido por la API en `inmueblebot-api.onrender.com`) guarda cookies en el SUYO.
- `web/render.yaml:17`: `DASHBOARD_URL` apunta a un **placeholder `localhost:5173`**
  — tras loguear en la landing no llegás al dashboard real.
- La landing **no tiene** botón "Continuar con Google".
- El primer login con Google crea tenant+trial al instante (auto-signup), sin pedir
  el nombre de la inmobiliaria.

### Restricción técnica clave

`onrender.com` está en la **Public Suffix List** → es IMPOSIBLE compartir cookies
entre `viviendapp-web.onrender.com` y `inmueblebot-api.onrender.com` (el browser
rechaza `Domain=.onrender.com`). La sesión debe cruzar de la landing al dashboard
por **handoff token**, no por cookie compartida. (Con dominio custom futuro, esto
se simplifica, pero el handoff sigue funcionando igual.)

---

## 1. Arquitectura objetivo

```
                         ┌──────────────────────────────┐
  usuario ──────────────►│ LANDING viviendapp-web        │  único login/signup
                         │  /login  /signup  (+ Google)  │
                         └──────┬───────────────┬───────┘
                                │ email+pass     │ Google
                                ▼                ▼
                  BFF /api/auth/login    API /auth/google/login (redirect)
                                │                │
                                ▼                ▼ callback
                  API /auth/login        ¿cuenta existe?
                                │           ├─ sí → cookies API + dashboard
                                ▼           └─ no → landing /signup/complete
                  POST /auth/handoff-code        (pide nombre inmobiliaria)
                                │                       │
                                ▼                       ▼
                  GET API /auth/handoff?code=…   POST /auth/google/complete
                     (cookies API + redirect)    (crea tenant+trial, handoff)
                                │                       │
                                ▼                       ▼
                         ┌──────────────────────────────┐
                         │ DASHBOARD (API origin)        │
                         │ anon → redirige a landing     │
                         └──────────────────────────────┘
```

**Regla de oro:** el dashboard nunca muestra login propio en producción; toda
autenticación entra por la landing. El form actual de `Login.jsx` queda solo como
fallback de desarrollo (sin `VITE_LOGIN_URL`) y de emergencia anti-loop.

---

## 2. Fase A — Handoff de sesión (API)

El puente seguro entre la sesión de la landing y las cookies del dashboard.

### A.1 Token de handoff

- JWT firmado con la infra existente (`app/core/security.py`), `type="handoff"`,
  claims `{sub, tid, role, jti}`, **TTL 60 segundos**.
- **Single-use vía Redis**: en el canje, `SET handoff:used:{jti} 1 NX EX 90`; si la
  key ya existía → rechazar (replay). Redis ya es infra core del proyecto.
- Nunca contiene el refresh token; si se filtra en un log de URL, expira en 60 s y
  solo sirve una vez.

### A.2 Endpoints nuevos (`app/api/routes/auth.py`)

```
POST /auth/handoff-code   (auth: Bearer o cookie de access)
  → { "code": "<jwt handoff>" }

GET  /auth/handoff?code=<jwt>     (navegación top-level desde la landing)
  → valida firma+exp+type → SETNX jti en Redis → carga cuenta →
    _set_auth_cookies() en el origen de la API → 303 a "/" (dashboard)
  → en error: 303 a {PUBLIC_APP_URL}/login?error=handoff  (la landing muestra
    mensaje; NUNCA loop al dashboard)
```

Helpers nuevos en `app/core/security.py`: `create_handoff_token(account)` (reusa
`_encode`). Rate limit: mismo límite que `/auth/login`.

---

## 3. Fase B — Google con registro explícito (API)

Cambia el caso "email nuevo" del callback: de auto-crear → a pedir el nombre.

### B.1 `auth_service.py` — partir `login_or_signup_google()` en dos

```
login_google(claims) -> TenantAccount | None
  · match por google_sub → login
  · match por email (verificado) → link + login
  · sin match → devuelve None   (YA NO crea nada)

complete_google_signup(registration_token, agency_name) -> TenantAccount
  · valida el registration token (type="g_signup", single-use Redis, TTL 15 min)
  · crea Tenant + Subscription(trial) + TenantAccount(password_hash=NULL,
    google_sub, email_verified_at=now)  ← el código que hoy vive en el branch 4
```

### B.2 Registration token

JWT `type="g_signup"`, claims `{gsub, email, name, jti}`, TTL 15 min, single-use en
Redis (`gsignup:used:{jti}`). Solo permite CREAR una cuenta con esa identidad
Google ya verificada — no abre sesión de nada existente.

### B.3 `GET /auth/google/callback` — nuevo branch

```
account = login_google(claims)
si account → cookies + 303 "/"                  (igual que hoy)
si None    → reg_token = create_google_signup_token(claims)
             303 {PUBLIC_APP_URL}/signup/complete?gt=<reg_token>
```

### B.4 Endpoint de completado

```
POST /auth/google/complete   body: { token: str, agency_name: str (2..200) }
  → complete_google_signup() → TokenResponse + Set-Cookie (origen API)
  → errores: 400 token inválido/usado/expirado · 409 email ya registrado
    (carrera: alguien registró ese email entre el callback y el submit)
```

CORS: ya permite `PUBLIC_APP_URL` con credenciales (main.py:190) — verificar que
`PUBLIC_APP_URL` en Render apunte a `https://viviendapp-web.onrender.com`.

---

## 4. Fase C — Landing (`web/`)

### C.1 Botón "Continuar con Google" (login + signup)

Anchor simple en ambas páginas `(auth)/login` y `(auth)/signup`:
`href = {NEXT_PUBLIC_API_URL}/auth/google/login` (navegación top-level; el flujo
entero vive en la API). Mismo ícono G multicolor que ya tiene el dashboard
(`dashboard/src/Login.jsx` → componente `GoogleIcon`, portarlo a TSX).

### C.2 Post-login/signup con contraseña → handoff al dashboard

En los BFF routes `web/src/app/api/auth/{login,signup}/route.ts`, tras obtener
los tokens de la API:

```ts
const handoff = await apiPost('/auth/handoff-code', {}, result.data.access_token)
return NextResponse.json({ ok: true,
  next: `${API_URL}/auth/handoff?code=${handoff.data.code}` })
```

El cliente hace `window.location.assign(next)`. (Se conservan también las cookies
de la landing via `setAuthCookies()` — sirven para páginas autenticadas futuras de
la landing, ej. gestión de suscripción.)

### C.3 Página nueva `/signup/complete`

- Lee `?gt=` (registration token), muestra un único campo "Nombre de tu
  inmobiliaria" + el email de Google (decodificar el JWT client-side SOLO para
  display — la validación real es server-side).
- Submit → BFF `POST /api/auth/google-complete` → API `/auth/google/complete` →
  recibe tokens → pide handoff-code → `window.location.assign(handoff)`.
- Token expirado/usado → mensaje + botón "Volver a intentar con Google".

### C.4 Página `/login` — errores de OAuth

Manejar `?error=handoff|oauth|state|email_unverified|suspended` con los mismos
mensajes que ya tiene `dashboard/src/Login.jsx` (`OAUTH_ERRORS`).

### C.5 Config

`web/render.yaml`: `DASHBOARD_URL` = `https://inmueblebot-api.onrender.com/dashboard`
(reemplaza el placeholder localhost). Verificar dónde se usa (`grep DASHBOARD_URL web/src`).

---

## 5. Fase D — Dashboard (redirigir anon a la landing)

### D.1 `dashboard/src/main.jsx` (o `Login.jsx`)

```jsx
const LOGIN_URL = import.meta.env.VITE_LOGIN_URL;  // ej: https://viviendapp-web.onrender.com/login
// status === 'anon':
//   si LOGIN_URL && !sessionStorage.getItem('login_redirected'):
//        sessionStorage.setItem('login_redirected', '1');
//        window.location.replace(LOGIN_URL);
//   si no → render <Login /> (fallback dev / anti-loop)
```

- **Guard anti-loop**: si el handoff falla y volvemos anon, el flag de
  `sessionStorage` evita rebotar infinito landing↔dashboard; segunda vez se muestra
  el form local. Limpiar el flag en login exitoso (`status === 'authed'`).
- Logout (`Topbar`) → tras `POST /auth/logout`, `window.location.assign(LOGIN_URL)`.

### D.2 Build

Root `Dockerfile` stage 1: `ARG VITE_LOGIN_URL` + `ENV` antes de `npm run build`
(Vite congela env en build-time). Render: agregar la env var al servicio.

### D.3 Limpieza

El botón Google del dashboard y su form quedan SOLO en el fallback dev. El
callback de Google sigue aterrizando en el dashboard ("/") — sin cambios.

---

## 6. Seguridad (checklist de implementación)

- [ ] Handoff: TTL 60 s, single-use Redis (SETNX), nunca contiene refresh token
- [ ] Registration token: TTL 15 min, single-use, solo crea (no loguea existentes)
- [ ] `/auth/handoff` y `/auth/google/complete` con rate limit de `/auth/login`
- [ ] Redirects de error SIEMPRE a `{PUBLIC_APP_URL}/login?error=…` (URL de config,
      jamás de query param → no open-redirect)
- [ ] 409 en `google/complete` si el email ya existe (carrera TOCTOU)
- [ ] CORS: `PUBLIC_APP_URL` correcto en Render (landing real, no localhost)
- [ ] Si Redis cae: handoff falla CERRADO (error visible), nunca acepta replay

## 7. Tests

- `tests/test_handoff.py`: code→cookies OK · replay rechazado · expirado · type mismatch
- `tests/test_google_oauth.py` (actualizar): callback con email nuevo → 303 a
  `/signup/complete` (ya NO crea cuenta) · `google/complete` crea tenant+trial ·
  token reusado → 400 · email tomado → 409 · existentes (sub/link) sin cambios
- E2E manual: landing login → dashboard · landing Google nuevo → completar nombre →
  dashboard · dashboard anon → redirect landing · logout → landing

## 8. Orden de implementación

| # | Tarea | Tamaño | Depende de |
|---|---|---|---|
| 1 | Fase A: handoff (security.py + 2 endpoints + Redis single-use + tests) | M | — |
| 2 | Fase B: split login_google/complete_google_signup + callback + endpoint + tests | M | — |
| 3 | Fase C: landing — Google buttons, handoff post-login, /signup/complete, DASHBOARD_URL | M | 1, 2 |
| 4 | Fase D: dashboard — redirect anon con guard anti-loop + VITE_LOGIN_URL en Dockerfile | S | 1 |
| 5 | Render: env vars (`VITE_LOGIN_URL`, verificar `PUBLIC_APP_URL`) + deploy ambos servicios | XS | 3, 4 |
| 6 | E2E manual de los 4 flujos + borrar flag sessionStorage en authed | XS | 5 |

**Sin migraciones nuevas** — el esquema de 0006 ya soporta todo esto.

## 9. Env vars (resumen post-implementación)

| Servicio | Var | Valor |
|---|---|---|
| inmueblebot-api | `PUBLIC_APP_URL` | `https://viviendapp-web.onrender.com` ← VERIFICAR |
| inmueblebot-api | `GOOGLE_OAUTH_*` (3) | ya configuradas (fase anterior) |
| inmueblebot-api (build) | `VITE_LOGIN_URL` | `https://viviendapp-web.onrender.com/login` |
| viviendapp-web | `DASHBOARD_URL` | `https://inmueblebot-api.onrender.com/dashboard` |
| viviendapp-web | `API_URL` / `NEXT_PUBLIC_API_URL` | ya correctas |

## 10. Notas

- **Tenant de prueba del owner** (creado 2026-06-10 con Google personal): se
  conserva; el trial vence solo a los 14 días. Tras implementar la Fase B, ese
  flujo de auto-creación deja de existir.
- **Pendiente de ops (independiente)**: rotar la API key de Render que está en
  texto plano en `.claude/settings.local.json:32`.
- Migración futura a dominio custom (`viviendapp.com` + `app.viviendapp.com`):
  el handoff sigue funcionando tal cual; solo cambian las URLs de config. Si se
  quisiera, ahí se puede pasar a cookie compartida `Domain=.viviendapp.com` y
  retirar el handoff, pero no es necesario.
