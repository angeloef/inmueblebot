# Plan: Google OAuth + Recuperación de cuenta + Persistencia de sesión

> **Estado:** ✅ IMPLEMENTADO (2026-06-10) — código en main. Falta solo el setup de
> credenciales en Google Cloud Console + env vars en Render + `alembic upgrade head`.
> **Fecha:** 2026-06-10
> **Alcance:** (1) login/signup con Google como método adicional, (2) recuperación de
> cuenta garantizada con cualquier método de login, (3) fix de la sesión que se
> pierde al recargar el dashboard.

---

## ⚙️ Pasos manuales para activar Google login (lo único que falta)

1. **Google Cloud Console** → APIs & Services → Credentials → Create OAuth client ID
   → tipo **"Web application"**. Authorized redirect URI (EXACTO):
   `https://inmueblebot-api.onrender.com/api/auth/google/callback`
2. **Render** (env vars del servicio `inmueblebot-api`):
   - `GOOGLE_OAUTH_CLIENT_ID` = el client ID
   - `GOOGLE_OAUTH_CLIENT_SECRET` = el client secret
   - `GOOGLE_OAUTH_REDIRECT_URI` = `https://inmueblebot-api.onrender.com/api/auth/google/callback`
   - (opcional) `GOOGLE_OAUTH_SUCCESS_PATH` = `/` (default ya correcto)
3. **Migración:** `alembic upgrade head` (aplica `0006_google_oauth`: `google_sub` +
   password_hash nullable). Aditiva e idempotente.
4. Mientras las env vars estén vacías, `/auth/google/*` devuelve 501 y el botón del
   dashboard simplemente falla con un mensaje — no rompe el login con contraseña.

> **Nota de implementación:** se usó httpx + google-auth (ya en requirements) en lugar
> de Authlib/SessionMiddleware que pedía el plan original — menos dependencias nuevas
> (cero) y reusa la infra JWT existente para el state anti-CSRF.

---

## 0. Diagnóstico previo (sesión que se pierde al recargar)

Se testeó la API live (`inmueblebot-api.onrender.com`) con curl. **El backend funciona
correctamente** — el problema NO está en el servidor:

| Test | Resultado |
|---|---|
| `POST /auth/signup` → atributos de cookies | ✅ `vivienda_access` Max-Age=3600, `vivienda_refresh` Max-Age=604800, ambas `HttpOnly; Path=/; SameSite=lax; Secure` — **persistentes**, sobreviven reload |
| `GET /auth/me` con cookie | ✅ 200 |
| `POST /auth/refresh` sin body, solo cookie | ✅ 200, rota ambas cookies |
| `GET /api/auth/me` (ruta compat del bundle) | ✅ 200 |
| Bundle desplegado (`index-Do45yWBu.js`) | ✅ contiene el interceptor de refresh (`auth/refresh`, `auth:expired`) |

**Conclusión:** la pérdida de sesión ocurre en el browser. Causas candidatas, en orden
de probabilidad:

1. **Origen distinto**: las cookies se setean en el dominio de la API. Si el dashboard
   se abre desde otro host (p. ej. localhost:5173 en dev, o un dominio custom que no
   proxea `/api` al mismo origen), las cookies `SameSite=lax` no viajan o no se guardan.
2. **Cold start de Render**: el plan free suspende el servicio. Al recargar tras
   inactividad, el primer `GET /auth/me` falla por **error de red/timeout** (no 401).
   `loadMe()` en `dashboard/src/auth.jsx:33` trata *cualquier* error como `anon` →
   muestra login aunque las cookies estén perfectas.
3. **Cookies de terceros bloqueadas** si el dashboard se embebe (iframe) — descartable
   si se accede directo.

**Verificación manual (5 min, hacer antes de implementar):** loguearse en el dashboard,
abrir DevTools → Application → Cookies → verificar que `vivienda_access` y
`vivienda_refresh` existen en el origen del dashboard. Recargar y mirar en Network si
`/auth/me` devuelve 401, error de red, o nunca lleva cookies. Eso decide cuál de los
3 candidatos es (la Parte C cubre los tres igualmente).

---

## Parte A — Google OAuth (login + signup)

### A.1 Decisiones de diseño

- **Librería:** [Authlib](https://docs.authlib.org/en/latest/client/fastapi.html)
  (`authlib`, integración nativa con Starlette/FastAPI). Flujo Authorization Code +
  PKCE + verificación de `id_token` contra las JWKS de Google.
- **Modelo de identidad:** columna `google_sub` en `tenant_accounts` (no una tabla
  `account_identities` aparte — YAGNI con 2 proveedores; migrar a tabla si algún día
  se suman Microsoft/Apple).
- **Emisión de sesión:** el callback emite **exactamente las mismas cookies httpOnly**
  que `/auth/login` (reusa `_token_response` + `_set_auth_cookies` de
  `app/api/routes/auth.py`). El dashboard no nota la diferencia: `loadMe()` ya la
  levanta sola al volver del redirect.
- **Signup automático:** si el email de Google no existe, se crea Tenant +
  Subscription(trial) + TenantAccount en el callback usando el `name` del perfil de
  Google como `agency_name` provisorio (renombrable en Configuración). KISS — evita
  una pantalla intermedia de "completá tu inmobiliaria". *(Alternativa descartada:
  token de registro de corta vida + form de agency_name; más limpio en UX pero suma
  2 endpoints y estado intermedio.)*

### A.2 Cambios de base de datos — migración `0006_google_oauth`

```sql
-- tenant_accounts
ALTER TABLE tenant_accounts ALTER COLUMN password_hash DROP NOT NULL;  -- cuentas Google-only
ALTER TABLE tenant_accounts ADD COLUMN IF NOT EXISTS google_sub TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_accounts_google_sub
    ON tenant_accounts (google_sub) WHERE google_sub IS NOT NULL;
```

Mismo patrón idempotente que `0005`. `downgrade()`: drop índice + columna; el
`SET NOT NULL` de password_hash NO se restaura en downgrade (habría filas NULL).

ORM (`app/db/models/...` donde vive `TenantAccount`):
- `password_hash: Mapped[str | None]`
- `google_sub: Mapped[str | None]`

### A.3 Config (`app/core/config.py`)

```python
GOOGLE_OAUTH_CLIENT_ID: str = Field(default="", description="OAuth client ID (login con Google)")
GOOGLE_OAUTH_CLIENT_SECRET: str = Field(default="", description="OAuth client secret")
FRONTEND_BASE_URL: str = Field(default="", description="URL a la que redirigir tras el callback (default: mismo origen)")
```

> **Ojo:** son credenciales NUEVAS de Google Cloud Console (tipo "Web application"),
> distintas de las del Calendar OAuth que ya existen en config (líneas ~338-346).
> Redirect URIs autorizadas: `https://inmueblebot-api.onrender.com/auth/google/callback`
> (+ `http://localhost:8000/auth/google/callback` para dev).
> Si las env vars están vacías → los endpoints devuelven 501 y el botón no se
> muestra en el front (feature flag implícito).

### A.4 Endpoints nuevos (`app/api/routes/auth.py`)

```
GET /auth/google/login     → redirect 302 a Google (genera state + nonce, PKCE)
GET /auth/google/callback  → valida state, canjea code, verifica id_token,
                             resuelve cuenta, setea cookies, redirect 302 al dashboard
```

Registro de Authlib (una vez, módulo-level o en `create_app`):

```python
from authlib.integrations.starlette_client import OAuth
oauth = OAuth()
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
    client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)
```

> Authlib guarda `state`/`nonce` en `request.session` → requiere agregar
> `SessionMiddleware` (Starlette) con un secret propio en `main.py`. La cookie de
> sesión solo se usa durante el handshake OAuth (no para la sesión del dashboard,
> que sigue siendo JWT).

**Lógica del callback** (nueva función `auth_service.login_or_signup_google(claims)`):

```
claims = id_token verificado → {sub, email, email_verified, name}

1. SI email_verified is not True → 403 (nunca auto-linkear emails no verificados)
2. account = SELECT ... WHERE google_sub = :sub
   → existe: login (saltar a 5)
3. account = SELECT ... WHERE email = :email (lower)
   → existe: LINKEAR → account.google_sub = sub;
     si email_verified_at es NULL → setearlo ahora (Google ya verificó el email)
   → login (saltar a 5)
4. No existe → signup automático:
   - reusar la transacción de auth_service.signup() pero con
     password_hash=NULL, google_sub=sub, email_verified_at=now
   - agency_name = claims["name"] o el local-part del email
   - tenant.status="trial" + Subscription trial (idéntico al signup actual)
5. Verificar tenant.status != "suspended" (mismo check que authenticate())
6. Emitir cookies (reusar _token_response + _set_auth_cookies)
7. Redirect 302 → FRONTEND_BASE_URL or "/"
```

### A.5 Cambios en el login con contraseña

`auth_service.authenticate()` (`app/services/auth_service.py:90`):

```python
if account is None or account.password_hash is None:
    verify_password(password, _DUMMY_HASH)   # timing-safe, ya existe el patrón
    raise InvalidCredentials()
```

(Hoy `password_hash is None` rompería `verify_password` — hay que cubrirlo
explícitamente, manteniendo el dummy-hash contra user enumeration.)

### A.6 Frontend

**`dashboard/src/Login.jsx`:**
- Botón "Continuar con Google" (debajo del form, separador "o"):
  `window.location.href = ${API_BASE}/auth/google/login`
- Sin cambios en `auth.jsx`: al volver del redirect, el `loadMe()` del mount
  encuentra las cookies ya seteadas.
- Mostrar mensaje de error si la URL trae `?error=oauth` (el callback redirige con
  ese query param en caso de fallo, en vez de mostrar JSON crudo).

**`web/` (landing Next.js):** mismo botón en su pantalla de login/signup apuntando a
los mismos endpoints. **Fase separada** — el BFF de la landing maneja tokens por body
JSON; el flujo redirect le es ortogonal pero hay que verificar a qué origen redirige
el callback. No bloquea el dashboard.

### A.7 Seguridad (checklist de la implementación)

- [ ] `state` anti-CSRF + `nonce` anti-replay (Authlib lo hace; verificar que
      `SessionMiddleware` tenga `same_site="lax"` y `https_only=True` en prod)
- [ ] `id_token` verificado contra JWKS de Google (firma, `aud`, `iss`, `exp`) —
      **nunca** confiar en el endpoint userinfo sin verificar firma
- [ ] Auto-link solo con `email_verified=true` del claim (paso 1 del callback)
- [ ] El redirect post-callback es a una URL fija de config — **no** aceptar un
      parámetro `next`/`redirect_to` del request (open redirect)
- [ ] Rate limit en `/auth/google/*` (mismo límite que `/auth/login`)
- [ ] `GOOGLE_OAUTH_CLIENT_SECRET` solo por env var en Render — jamás en el repo

---

## Parte B — Recuperación de cuenta con cualquier método

**Objetivo:** perder el acceso por un método nunca bloquea la cuenta.

| Escenario | Cómo se recupera | Estado |
|---|---|---|
| Cuenta email+password, olvidó la contraseña | `/auth/forgot-password` → email con token single-use (`token_version`) | ✅ ya existe |
| Cuenta email+password, pierde acceso al email | Sin recovery posible (correcto: el email ES la identidad) | ✅ por diseño |
| Cuenta Google-only, pierde la cuenta Google | `forgot-password` con su email → `reset-password` **establece su primera contraseña** (`password_hash` NULL → valor). A partir de ahí tiene ambos métodos | ⚠️ funciona casi gratis con el flujo actual — `forgot_password` no chequea `password_hash`, así que ya enviaría el mail; agregar test que lo garantice |
| Cuenta password, quiere sumar Google | Login con Google con el mismo email → auto-link (paso 3 del callback) | se implementa en Parte A |
| Cuenta Google, quiere sumar contraseña | Opción 1 (gratis): usar forgot-password. Opción 2 (mejor UX): sección "Seguridad" en Configuración del dashboard con "Establecer contraseña" + "Estado: Google vinculado ✓" | Opción 1 sale gratis; opción 2 es fase posterior |

**Regla invariante:** `email` (verificado) es la clave de identidad que une métodos.
Por eso el auto-link exige `email_verified=true` y por eso un cambio de email de
cuenta (si algún día se implementa) deberá re-verificar antes de aplicarse.

**Cambio mínimo requerido:** exponer en `GET /auth/me` un campo
`auth_methods: ["password", "google"]` (derivado de `password_hash is not None` /
`google_sub is not None`) para que el dashboard pueda mostrar el estado y sugerir
agregar el segundo método. Costo: 3 líneas en `MeResponse`.

---

## Parte C — Mantener la sesión activa (fix del reload → login)

La arquitectura ya es correcta (access 60 min + refresh 7 días con rotación =
ventana deslizante). Los fixes atacan los 3 candidatos del diagnóstico:

### C.1 `auth.jsx` — distinguir "no autenticado" de "no hay red" (fix principal)

Hoy (`dashboard/src/auth.jsx:28-37`) cualquier excepción → `anon` → login. Un cold
start de Render (50s) o un corte de red expulsa a un usuario con cookies válidas.

```jsx
const loadMe = useCallback(async (attempt = 0) => {
  try {
    const data = await authApi.me();
    setMe(data); setStatus('authed');
  } catch (err) {
    if (err?.response?.status === 401) {       // sesión realmente inválida
      setMe(null); setStatus('anon');          // (el interceptor ya intentó refresh)
      return;
    }
    // Error de red / 5xx / cold start → reintentar con backoff, NO ir al login
    if (attempt < 4) {
      setStatus('loading');                    // o un estado 'reconnecting' con UI propia
      setTimeout(() => loadMe(attempt + 1), Math.min(2000 * 2 ** attempt, 15000));
    } else {
      setMe(null); setStatus('anon');          // rendirse tras ~45s
    }
  }
}, []);
```

UI: mientras reintenta, mostrar "Conectando con el servidor…" en vez del login
(en `App.jsx`/`Shell.jsx`, donde se decide qué renderizar según `status`).

### C.2 Refresh proactivo (evita el 401 visible a los 60 min)

En `AuthProvider`, un `setInterval` que postee `/auth/refresh` cada **50 minutos**
mientras `status === 'authed'` (y un refresh inmediato en el evento
`visibilitychange` → visible, para pestañas que durmieron). El interceptor reactivo
queda como red de seguridad. ~15 líneas.

### C.3 Extender la ventana de sesión

`REFRESH_TOKEN_TTL_DAYS: 7 → 30` en config (env var en Render). Con la rotación en
cada refresh, un usuario activo no vuelve a ver el login nunca; uno inactivo 30 días,
sí. El access token queda en 60 min (no tocar: limita el daño de un access robado).

### C.4 Garantizar mismo-origen (si el diagnóstico manual confirma el candidato 1)

El dashboard DEBE consumirse desde el mismo origen que setea las cookies
(`inmueblebot-api.onrender.com` o el dominio custom que proxee `/api`). Si hoy se
accede por otro host: o se mueve el acceso, o se cambia a `SameSite=None; Secure` +
`allow_credentials` CORS explícito (menos seguro, evitarlo si el proxy es viable).
**Decisión post-diagnóstico manual.**

---

## Orden de implementación

| # | Tarea | Tamaño | Depende de |
|---|---|---|---|
| 1 | C.1 + C.2 (auth.jsx resiliente + refresh proactivo) | S | — |
| 2 | C.3 (env var TTL 30d en Render) | XS | — |
| 3 | Diagnóstico manual del browser (5 min) → decide si hace falta C.4 | XS | — |
| 4 | Migración 0006 + ORM (`google_sub`, password_hash nullable) | S | — |
| 5 | A.5 (authenticate con password_hash NULL, timing-safe) + tests | S | 4 |
| 6 | Config + SessionMiddleware + endpoints Google + `login_or_signup_google()` + tests | M | 4, 5 |
| 7 | Botón Google en `Login.jsx` + manejo `?error=oauth` | S | 6 |
| 8 | `auth_methods` en `/auth/me` + test del flujo recovery Google-only→password | S | 4 |
| 9 | Deploy: credenciales en Google Cloud Console + env vars en Render + `alembic upgrade head` | XS | 6 |
| 10 | (Fase posterior) Botón Google en landing `web/` + sección "Seguridad" en Configuración | M | 6 |

**Tests clave (pytest, mockeando el id_token de Google):**
- callback con `sub` conocido → login, cookies seteadas
- callback con email existente (cuenta password) → auto-link, `google_sub` poblado
- callback con email nuevo → tenant+subscription+account creados, trial activo
- callback con `email_verified=false` → 403, sin link
- `authenticate()` con `password_hash=None` → InvalidCredentials (sin crash)
- `reset-password` sobre cuenta Google-only → establece password, login con ambos métodos funciona
- state inválido en callback → 4xx

**Rollback:** los endpoints Google quedan detrás del check de env vars vacías → 501.
Desactivar = borrar las env vars. La migración 0006 es aditiva (downgrade limpio).
