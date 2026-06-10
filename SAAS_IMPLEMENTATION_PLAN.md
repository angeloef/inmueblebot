# ViviendApp — Plan de implementación SaaS self-serve

> Documento maestro para ejecutar con **Claude Code**. Convierte InmuebleBot en un SaaS
> multi-tenant con landing pública, registro/login, suscripción de pago y dashboard por
> inmobiliaria. Cada tarea indica el **skill ECC** a usar.
>
> **Generado:** 2026-06-09 · **Stack:** FastAPI + Postgres (RLS) + Redis · React/Vite · Next.js
> **Memoria relacionada:** `project-saas-landing-plan.md`

---

## 0. Decisiones fijas (NO re-litigar)

| Tema | Decisión |
|---|---|
| **Auth** | JWT propio en FastAPI. Tabla nueva `tenant_accounts` (login de la inmobiliaria), separada de `users` (clientes de WhatsApp). |
| **Pago** | MercadoPago **suscripción recurrente (preapproval)** + webhook que sincroniza `tenants.status`. |
| **Modelo comercial** | **Trial gratis 14 días** (`TRIAL_DAYS`, configurable) → al vencer se exige suscripción o se suspende. |
| **Email** | **Resend** (verificación de cuenta + reset de password). |
| **Landing** | **Next.js** Web Service nuevo en Render (servicio aparte). |
| **Dashboard** | **Camino A**: el dashboard Vite actual se queda; se le agrega login JWT + scoping por tenant. |
| **WhatsApp** | NO se buscan clientes hasta ser **Meta Tech Provider**. En el build solo va un **placeholder** en la app; el Embedded Signup real es la Fase 5. |

---

## 1. Cómo usar este documento

- Las fases son **secuenciales** salvo la Fase 0 (corre en paralelo) y la Fase 5 (gated en Meta).
- Cada tarea tiene: **Skill ECC**, archivos, qué hacer, criterios de aceptación y verificación.
- **Invocar el skill ECC** con la herramienta `Skill` (ej: `ecc:backend-patterns`) ANTES de escribir
  el código de esa tarea — informa el diseño. Los `*-review`/`security-review` se corren DESPUÉS,
  sobre el diff.
- **Regla de oro de seguridad:** toda tarea que toque auth, tokens, pagos o PII corre
  `ecc:security-review` sobre su diff antes de dar por cerrada la tarea.

### Catálogo ECC disponible (verificado en disco)

`backend-patterns` · `api-design` · `frontend-patterns` · `nextjs-turbopack` ·
`security-review` · `tdd-workflow` · `e2e-testing` · `verification-loop` ·
`documentation-lookup` · `coding-standards`

> ⚠️ No existen skills por lenguaje (`python-review`, `fastapi-review`). El catálogo es temático.

---

## 2. Arquitectura de servicios (Render)

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  viviendapp-web (NUEVO)     │  JWT    │  inmueblebot-api (EXISTENTE)  │
│  Next.js Web Service        │ ──────► │  FastAPI Web Service          │
│  • Landing pública (SEO)    │         │  • Bot + webhook WhatsApp     │
│  • /login /signup /precios  │         │  • API /admin/* (existe)      │
│  • /checkout (MercadoPago)  │ ◄────── │  • NUEVO: /auth /billing /wa  │
└─────────────────────────────┘ redirect└──────────────────────────────┘
                                          │ Postgres (RLS multi-tenant ✓)
                                          │ Redis (namespaced x tenant ✓)
  Dashboard Vite existente → sigue servido por FastAPI, + login JWT (Fase 4)
```

**Pieza clave:** el multi-tenant ya funciona vía ContextVar
([`app/core/tenancy.py`](app/core/tenancy.py) → `set_current_tenant`). Apenas el JWT llame a
ese ContextVar, RLS + namespacing de Redis se aplican solos
([`app/db/tenant_session.py`](app/db/tenant_session.py)). **No se reescribe el data layer.**

---

## 3. Variables de entorno nuevas

### Backend (FastAPI)
```
# Auth / JWT
SECRET_KEY=<cambiar el default "change-me-in-production">   # ⚠️ config.py:82
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_MIN=30
REFRESH_TOKEN_TTL_DAYS=30
TRIAL_DAYS=14

# MercadoPago
MERCADOPAGO_ACCESS_TOKEN=<prod token>
MERCADOPAGO_WEBHOOK_SECRET=<secret de la notificación>
MP_PLAN_PRICE_ARS=<precio mensual>

# Email (Resend)
RESEND_API_KEY=<key>
EMAIL_FROM="ViviendApp <no-reply@tudominio.com>"

# Meta Embedded Signup (Fase 5)
META_APP_ID=<app id>
META_APP_SECRET=<app secret>
META_EMBEDDED_CONFIG_ID=<config id de FB Login for Business>

# URLs
PUBLIC_APP_URL=https://viviendapp-web.onrender.com
PUBLIC_API_URL=https://inmueblebot-api.onrender.com

# Ya existentes (verificar seteados)
TENANT_TOKEN_ENCRYPTION_KEY=<fernet key>
ADMIN_API_KEY=<super-admin key>
DEFAULT_TENANT_ID=00000000-0000-0000-0000-000000000001
```

### Next.js (viviendapp-web)
```
NEXT_PUBLIC_API_URL=https://inmueblebot-api.onrender.com
NEXT_PUBLIC_META_APP_ID=<app id>          # Fase 5
NEXT_PUBLIC_META_CONFIG_ID=<config id>    # Fase 5
```

---

## FASE 0 — Prerrequisitos (EN PARALELO, desde el día 1)

### Tarea 0.1 — Iniciar verificación Meta Tech Provider
- **Skill ECC:** `ecc:documentation-lookup` (docs de Meta WhatsApp Cloud API / Embedded Signup)
- **Qué hacer (manual, owner):** crear/verificar Meta App con producto WhatsApp, iniciar
  **Business Verification**, solicitar acceso avanzado a `whatsapp_business_management` y
  `whatsapp_business_messaging`, configurar **Facebook Login for Business** y obtener `config_id`.
- **Por qué primero:** tarda semanas y bloquea la Fase 5. El resto del SaaS avanza sin esto.
- **Aceptación:** app en proceso de review; `META_APP_ID`/`META_APP_SECRET` disponibles.

### Tarea 0.2 — Generar y setear secrets
- **Skill ECC:** `ecc:security-review`
- **Qué hacer:** generar `SECRET_KEY` fuerte, confirmar `TENANT_TOKEN_ENCRYPTION_KEY` y
  `ADMIN_API_KEY` en Render. **Nunca** dejar `SECRET_KEY` en el default.
- **Aceptación:** `python -c "from app.core.config import get_settings; assert get_settings().SECRET_KEY != 'change-me-in-production'"` pasa.

---

## FASE 1 — Backend Auth (JWT + tenant_accounts) ✅ COMPLETADA (2026-06-09)

> Núcleo del SaaS. Desbloquea todo. Al terminar, un tenant puede registrarse, loguearse y
> obtener un JWT que activa su contexto multi-tenant.
>
> **Estado:** implementada y verificada (imports OK, ruff limpio, 4 tests unitarios verdes;
> los 4 tests de DB se saltan sin Postgres local). Archivos: `app/db/models/tenant_account.py`,
> `app/db/models/subscription.py`, `alembic/versions/0004_auth_billing.py`, `app/core/security.py`,
> `app/api/deps.py`, `app/services/auth_service.py`, `app/services/email_service.py`,
> `app/api/routes/auth.py`, `tests/test_auth.py` (+ config/session/main).
>
> **Security review aplicada (`security-review`):**
> - **F-01 (HIGH):** `/auth/refresh` ahora recarga el account de DB (role real + chequeo de
>   suspensión) — ya no confía en el claim del refresh token.
> - **F-02 (HIGH):** `get_settings()` aborta el arranque en `ENVIRONMENT=production` si
>   `SECRET_KEY` quedó en el default inseguro.
> - **F-03 (MEDIUM):** tokens de reset son single-use vía `tenant_accounts.token_version`
>   (se valida y se incrementa al resetear).
> - F-04/F-05: preventivos, sin cambio (código actual correcto).
>
> **Pendiente al desplegar:** correr `alembic upgrade head` en Render; setear `SECRET_KEY`,
> `RESEND_API_KEY`, `PUBLIC_APP_URL`. Tests de DB requieren Postgres (`pytest tests/test_auth.py`).

### Tarea 1.1 — Modelo `TenantAccount`
- **Skill ECC:** `ecc:backend-patterns`
- **Archivo nuevo:** `app/db/models/tenant_account.py`
- **Qué hacer:** modelo SQLAlchemy con: `id` (UUID PK), `tenant_id` (FK→tenants, indexed),
  `email` (String, unique, indexed), `password_hash` (String), `full_name` (String|None),
  `role` (String, default `"owner"`; valores `owner|admin|superadmin`),
  `email_verified_at` (DateTime|None), `created_at`, `updated_at`.
- **Integración:** registrar en [`app/db/models/__init__.py`](app/db/models/__init__.py) para que
  `Base.metadata` lo conozca. NO es tenant-scoped por RLS (es la tabla de login); se accede
  antes de resolver tenant, igual que `tenants`.
- **Aceptación:** el modelo importa sin romper `Base.metadata`.

### Tarea 1.2 — Modelo `Subscription`
- **Skill ECC:** `ecc:backend-patterns`
- **Archivo nuevo:** `app/db/models/subscription.py`
- **Qué hacer:** `id` (UUID PK), `tenant_id` (FK, indexed), `provider` (default `"mercadopago"`),
  `mp_preapproval_id` (String|None, indexed), `mp_payer_id` (String|None),
  `status` (String: `trial|active|paused|cancelled|past_due`), `plan` (String|None),
  `amount` (Numeric|None), `currency` (default `"ARS"`),
  `trial_ends_at` (DateTime|None), `current_period_end` (DateTime|None), timestamps.
- **Integración:** registrar en `__init__.py`.
- **Aceptación:** importa OK.

### Tarea 1.3 — Migración Alembic 0004
- **Skill ECC:** `ecc:backend-patterns`
- **Archivo nuevo:** `alembic/versions/0004_auth_billing.py` (`down_revision = "0003_pgvector_knowledge"`)
- **Qué hacer:** crear tablas `tenant_accounts` y `subscriptions` con índices únicos
  (`email`, `mp_preapproval_id`). **Idempotente** (`IF NOT EXISTS` / guards), siguiendo el
  patrón de [`alembic/versions/0002_multitenancy.py`](alembic/versions/0002_multitenancy.py).
  NO aplicar RLS a estas tablas (login + billing se consultan sin contexto de tenant).
- **Verificación:** `alembic upgrade head` en una DB de prueba; `alembic downgrade -1` revierte.

### Tarea 1.4 — Utilidades de seguridad (hash + JWT)
- **Skill ECC:** `ecc:security-review` (diseño) + `ecc:backend-patterns`
- **Archivo nuevo:** `app/core/security.py`
- **Qué hacer:**
  - `hash_password(plain) -> str` y `verify_password(plain, hash) -> bool` con
    **argon2** o **bcrypt** vía `passlib` (agregar a `requirements.txt`).
  - `create_access_token(account) -> str`, `create_refresh_token(account) -> str`,
    `decode_token(token) -> dict` (HS256 con `SECRET_KEY`). Claims: `sub` (account_id),
    `tid` (tenant_id), `role`, `type` (access/refresh), `exp`.
- **Aceptación:** round-trip encode/decode; password mal verifica `False`.

### Tarea 1.5 — Dependency `get_current_account` (conecta auth ↔ multi-tenant)
- **Skill ECC:** `ecc:backend-patterns` + `ecc:security-review`
- **Archivo nuevo:** `app/api/deps.py`
- **Qué hacer:** dependency FastAPI que: lee `Authorization: Bearer <jwt>`, decodifica,
  carga el `TenantAccount`, y **llama `set_current_tenant(UUID(tid))`** de
  [`app/core/tenancy.py`](app/core/tenancy.py). Devuelve el account. Variante
  `require_role("superadmin")`. **Resetear el ContextVar al finalizar el request** (token de
  `set_current_tenant`) para no filtrar entre requests del pool.
- **Aceptación:** un request autenticado deja queries scopeadas al tenant correcto (RLS).
- ⚠️ **Crítico:** este es el punto donde el JWT enciende todo el RLS existente. Probar que un
  tenant NO ve datos de otro.

### Tarea 1.6 — Servicio de auth
- **Skill ECC:** `ecc:backend-patterns`
- **Archivo nuevo:** `app/services/auth_service.py`
- **Qué hacer:** `signup(email, password, agency_name)` → crea `Tenant` (status=`trial`,
  `trial_ends_at = now + TRIAL_DAYS`) + `Subscription` (status=`trial`) + `TenantAccount`
  (hash), en **una transacción**. `authenticate(email, password)` → valida y devuelve account.
  Manejar email duplicado (409). Generar `slug` único para el tenant a partir del nombre.
- **Aceptación:** signup crea las 3 filas atómicamente; email repetido falla limpio.

### Tarea 1.7 — Servicio de email (Resend)
- **Skill ECC:** `ecc:backend-patterns` + `ecc:documentation-lookup` (API Resend)
- **Archivo nuevo:** `app/services/email_service.py`
- **Qué hacer:** wrapper sobre Resend: `send_verification_email(account, token)` y
  `send_password_reset(account, token)`. Tokens firmados con `SECRET_KEY` (JWT corto, `type=verify`/`reset`).
  Si `RESEND_API_KEY` no está, loguear y no romper (degradar).
- **Aceptación:** con key de prueba, el email se envía; sin key, no rompe el signup.

### Tarea 1.8 — Router `/auth/*`
- **Skill ECC:** `ecc:api-design` + `ecc:security-review`
- **Archivo nuevo:** `app/api/routes/auth.py` · **registrar en** [`app/main.py`](app/main.py)
- **Endpoints:**
  - `POST /auth/signup` → crea cuenta, manda verificación, devuelve access+refresh.
  - `POST /auth/login` → devuelve tokens.
  - `POST /auth/refresh` → rota access token.
  - `GET /auth/me` → datos del account + tenant + estado de suscripción (usa `get_current_account`).
  - `POST /auth/forgot-password` / `POST /auth/reset-password`.
  - `GET /auth/verify-email?token=` → marca `email_verified_at`.
- **CORS:** agregar el dominio Next.js a `allow_origins` en [`app/main.py`](app/main.py:189).
- **Aceptación:** flujo signup→login→/auth/me funciona vía `curl`/test.

### Tarea 1.9 — Tests de auth
- **Skill ECC:** `ecc:tdd-workflow`
- **Archivo nuevo:** `tests/test_auth.py`
- **Qué hacer:** signup, login ok/mal, refresh, aislamiento entre tenants (un JWT de tenant A
  no lee datos de tenant B), expiración de token.
- **Verificación:** `pytest tests/test_auth.py -v`.

### ▶ Cierre Fase 1
- **Skill ECC:** `ecc:security-review` sobre todo el diff de auth, luego `ecc:verification-loop`.

---

## FASE 2 — Next.js: landing + páginas de auth ✅ COMPLETADA (2026-06-09)

> Servicio Render nuevo. Reconstruye el diseño del artifact ViviendApp como app real y
> conecta signup/login a la API.
>
> **Estado:** implementada y verificada (`npm run build` limpio — 0 errores TS, 16 rutas,
> middleware Edge compilado). 38 archivos en `web/` (Next.js 15 App Router + TS + Tailwind v3).
>
> **Patrón de seguridad aplicado:** el browser nunca ve el JWT. Las credenciales pasan por
> Route Handlers server-side (`web/src/app/api/auth/*`) que setean cookies **httpOnly + Secure
> (prod) + SameSite=Lax** (`vivienda_access`/`vivienda_refresh`). `middleware.ts` (Edge) protege
> `/app` y refresca el token proactivamente. `getSession` (setea cookies, solo route handlers)
> vs `getSessionReadOnly` (solo lee, para server components). Open-redirect del `?next=`
> bloqueado (solo rutas internas). Design tokens reales del artifact (primary #164a71, verdes
> WhatsApp, Manrope+Inter+JetBrains) en `tailwind.config.ts`.
>
> **Placeholders intencionales:** redirect al dashboard Vite cross-domain (Fase 4), checkout
> MercadoPago en Pricing (Fase 3), paso "Conectá tu WhatsApp (próximamente)" post-signup.
>
> **Pendiente al desplegar:** crear el Web Service en Render (ver `web/render.yaml`, rootDir
> `web/`); setear `NEXT_PUBLIC_API_URL`/`API_URL` a la URL del backend y `NEXT_PUBLIC_SITE_URL`;
> setear `PUBLIC_APP_URL` en el backend a la URL del web (links de email + CORS).

### Tarea 2.1 — Scaffold del proyecto Next.js
- **Skill ECC:** `ecc:nextjs-turbopack`
- **Directorio nuevo:** `web/` (monorepo; Render apunta su Root Directory a `web/`)
- **Qué hacer:** Next.js (App Router) + Tailwind. Cliente API (`web/lib/api.ts`) con `fetch`
  al `NEXT_PUBLIC_API_URL`, manejo de JWT en **cookie httpOnly** (no localStorage).
- **Aceptación:** `npm run dev` levanta; pega un `GET /health` a la API.

### Tarea 2.2 — Portar el diseño de la landing
- **Skill ECC:** `ecc:frontend-patterns`
- **Qué hacer:** reconstruir las secciones del artifact (`ViviendApp Landing Page.html`) como
  componentes React/Tailwind. Extraer los tokens de diseño (navy `#164a71`, fuentes Manrope+Inter).
  Optimizar imágenes (no base64 inline). Páginas: `/` (landing), `/precios`.
- **Aceptación:** landing responsive, Lighthouse SEO > 90.

### Tarea 2.3 — Páginas signup / login
- **Skill ECC:** `ecc:frontend-patterns` + `ecc:security-review`
- **Qué hacer:** `/signup` (nombre agencia, email, password) → `POST /auth/signup`;
  `/login` → `POST /auth/login`; guardar JWT en cookie httpOnly; middleware de Next que
  protege rutas y redirige según estado de suscripción. **Placeholder "Conectá WhatsApp"**
  como paso informativo post-signup (sin lógica real todavía).
- **Aceptación:** signup→checkout y login→dashboard redirigen bien.

### Tarea 2.4 — Deploy del servicio en Render
- **Skill ECC:** `ecc:nextjs-turbopack`
- **Qué hacer:** Web Service nuevo `viviendapp-web`, build `npm run build`, start `npm start`,
  env vars de la sección 3. Agregar su dominio al CORS del backend.
- **Aceptación:** landing pública accesible; signup contra la API de prod funciona.

---

## FASE 3 — MercadoPago: suscripción + gating + trial ✅ COMPLETADA (2026-06-09)

> Habilita cobrar. El estado de la suscripción gobierna el acceso al dashboard.
>
> **Estado:** implementada y verificada. Backend: 13 tests offline verdes (4 firma
> HMAC + 4 gating + 5 webhook/auth vía ASGI) + 2 tests de DB (transición de estado +
> idempotencia + expiración de trial) que se saltan sin Postgres; ruff limpio. Web:
> `npm run build` limpio (21 rutas, incluye `/checkout`, `/checkout/{success,failure,
> pending}`, `/api/billing/subscribe`).
>
> **Decisión de diseño:** `billing_service.py` NO se tocó — es el módulo de *cobranzas*
> de alquiler (IPC/punitorios), no de suscripción SaaS. La suscripción MercadoPago vive
> en **`app/services/subscription_service.py`** (módulo nuevo, dedicado).
>
> **Archivos:** `app/services/subscription_service.py` (preapproval + webhook sync +
> firma HMAC + gating puro + `mark_expired_trials`), `app/api/routes/billing.py`
> (`/billing/subscribe`, `/billing/status`, `/webhooks/mercadopago`), `app/api/deps.py`
> (`require_active_subscription` → 402), `app/core/config.py` (MP_* + PUBLIC_API_URL),
> `tests/test_billing.py`, y en `web/`: `app/api/billing/subscribe/route.ts`,
> `app/checkout/page.tsx` + `success|failure|pending`, `components/billing/{CheckoutButton,
> TrialBanner,CheckoutResult}.tsx`, banner de trial en `app/app/page.tsx`.
>
> **Flujo elegido:** preapproval *sin plan asociado* con `status="pending"` (sin
> card_token) → MercadoPago devuelve `init_point` y el usuario carga la tarjeta allí.
>
> ⚠️ **Producto MercadoPago = "Suscripciones", NO "Checkout Pro".** Son productos
> distintos: Checkout Pro (`POST /checkout/preferences`) **no soporta pagos recurrentes**;
> las suscripciones recurrentes usan la API de **preapproval** (`POST /preapproval`), que
> es lo que implementa `subscription_service.py`. En el panel de MercadoPago, al crear/
> configurar la app y los webhooks, elegir la pestaña **"Suscripciones" → "Suscripciones
> con integración"** (NO "Checkouts/Checkout Pro"). El backend ya es correcto: no hay
> cambio de código, solo de selección en el panel. El access token es el mismo por app.
>
> ✅ **Verificado en SANDBOX (2026-06-09) — integración probada end-to-end:**
> - App MercadoPago "ViviendApp" (id `6245975125066731`) creada como Suscripciones.
> - Webhook `subscription_preapproval` → `https://inmueblebot-api.onrender.com/webhooks/mercadopago`
>   configurado vía MCP de MercadoPago.
> - `/billing/subscribe` (prod en Render) genera preapproval real → `init_point` válido.
> - Pago autorizado con tarjeta de prueba → preapproval quedó **`status: authorized`**, cobro
>   **recurrente mensual** (`next_payment_date` seteado), monto 1000 ARS, sin dinero real.
> - **Lección de sandbox:** suscripciones exigen que collector y payer sean del **mismo tipo**;
>   en prueba el collector debe ser un **usuario de prueba vendedor** (sus credenciales de
>   *producción* funcionan como sandbox). En PRODUCCIÓN no aplica: cuenta real + pagador real.
>
> **Pendiente real para cobrar de verdad → ver [`PRODUCTION_LAUNCH_CHECKLIST.md`](PRODUCTION_LAUNCH_CHECKLIST.md):**
> token de **producción** (`APP_USR-…`) + secret de webhook de producción en Render, prueba con
> tarjeta real (monto bajo) → cancelar/reembolsar, y dominio propio para emails.
>
> **Security review aplicada (`security-review`):**
> - Firma `x-signature` validada con HMAC-SHA256 + `hmac.compare_digest` (tiempo constante).
> - **Fail-closed en producción:** sin `MERCADOPAGO_WEBHOOK_SECRET` el webhook devuelve 403.
> - **Hardening:** la firma se valida ANTES de parsear el body (no se parsea JSON de un
>   caller no autenticado).
> - Precio **server-authoritative** (`MP_PLAN_PRICE_ARS`), el cliente nunca elige el monto.
> - JWT nunca llega al browser: `/billing/subscribe` se hace vía Route Handler server-side
>   que reenvía la cookie httpOnly como Bearer.
> - Gating aislado por tenant: la suscripción se busca por el `tenant_id` del JWT.
> - Webhook idempotente (re-aplicar el mismo estado no cambia nada).
>
> **Pendiente al desplegar (manual, owner):**
> 1. Setear en Render: `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET`,
>    `MP_PLAN_PRICE_ARS`, `PUBLIC_API_URL`.
> 2. En MercadoPago → *Tus integraciones → Webhooks*: registrar
>    `https://<api>/webhooks/mercadopago` y copiar el secret de la firma.
> 3. (Opcional) `NEXT_PUBLIC_PLAN_PRICE_ARS` en el web para mostrar el precio en `/checkout`.
> 4. Probar el flujo con credenciales **sandbox** (TEST-...) antes de prod.

### Tarea 3.1 — Revisar/extender `billing_service.py`
- **Skill ECC:** `ecc:backend-patterns` + `ecc:documentation-lookup` (API preapproval MercadoPago)
- **Archivo:** [`app/services/billing_service.py`](app/services/billing_service.py) (YA existe — revisar y extender, no recrear)
- **Qué hacer:** `create_preapproval(tenant, plan)` → llama a MP, devuelve `init_point`.
  `sync_from_webhook(payload)` → mapea estado MP → `Subscription.status` + `tenants.status`
  (`active`/`paused`/etc.) y `current_period_end`.
- **Aceptación:** preapproval de sandbox devuelve `init_point` válido.

### Tarea 3.2 — Router `/billing/*`
- **Skill ECC:** `ecc:api-design` + `ecc:security-review`
- **Archivo nuevo:** `app/api/routes/billing.py` · registrar en `main.py`
- **Endpoints:**
  - `POST /billing/subscribe` (auth) → crea preapproval, devuelve `init_point`.
  - `GET /billing/status` (auth) → estado actual + `trial_ends_at`.
  - `POST /webhooks/mercadopago` (público, **valida firma** `MERCADOPAGO_WEBHOOK_SECRET`) →
    `sync_from_webhook`. Idempotente (puede llegar duplicado).
- **Aceptación:** webhook de sandbox actualiza el estado del tenant.

### Tarea 3.3 — Gating por estado de suscripción
- **Skill ECC:** `ecc:backend-patterns`
- **Qué hacer:** dependency `require_active_subscription` que permite acceso si
  `status in (trial no vencido, active)` y bloquea (402) si `trial` vencido o `paused`.
  Aplicar a las rutas del dashboard. Un job/check liviano marca trials vencidos.
- **Aceptación:** trial vencido sin pago → 402; tras pagar → acceso.

### Tarea 3.4 — Checkout en Next.js
- **Skill ECC:** `ecc:frontend-patterns`
- **Qué hacer:** `/checkout` → `POST /billing/subscribe` → redirige a `init_point`.
  Rutas de retorno `/checkout/success|failure|pending`. Banner de "trial: N días restantes"
  en el dashboard.
- **Aceptación:** flujo signup→checkout→pago sandbox→dashboard activo.

### Tarea 3.5 — Tests de billing
- **Skill ECC:** `ecc:tdd-workflow`
- **Archivo nuevo:** `tests/test_billing.py`
- **Qué hacer:** firma de webhook válida/ inválida, transición de estados, idempotencia,
  expiración de trial.
- **Verificación:** `pytest tests/test_billing.py -v`.

### ▶ Cierre Fase 3
- **Skill ECC:** `ecc:security-review` (foco: validación de firma del webhook, manejo de montos).

---

## FASE 4 — Dashboard Vite: JWT + scoping + placeholder WhatsApp

> El dashboard existente pasa de `x-api-key` global a login JWT por tenant.

### Tarea 4.1 — Login en el dashboard
- **Skill ECC:** `ecc:frontend-patterns`
- **Archivos:** [`dashboard/src/api.js`](dashboard/src/api.js), nuevo `dashboard/src/Login.jsx`,
  [`dashboard/src/App.jsx`](dashboard/src/App.jsx)
- **Qué hacer:** reemplazar el interceptor `x-api-key` ([api.js:22](dashboard/src/api.js:22)) por
  `Authorization: Bearer <jwt>`. Pantalla de login (o recibir el JWT por redirect desde Next.js).
  Guard de rutas; refresh de token; logout.
- **Aceptación:** el dashboard carga solo con JWT válido y muestra datos del tenant logueado.

### Tarea 4.2 — Migrar rutas admin a JWT
- **Skill ECC:** `ecc:backend-patterns` + `ecc:security-review`
- **Archivo:** [`app/api/routes/admin.py`](app/api/routes/admin.py:475)
- **Qué hacer:** cambiar `Depends(verify_admin_api_key)` por `Depends(get_current_account)` en
  las rutas de tenant. **Mantener `x-api-key`** solo para rutas de super-admin (gestión de
  tenants). Las queries quedan scopeadas solas por el ContextVar (Tarea 1.5).
- **Aceptación:** un account de tenant A no puede leer/editar datos de tenant B vía `/admin/*`.

### Tarea 4.3 — Placeholder de WhatsApp en Chats
- **Skill ECC:** `ecc:frontend-patterns`
- **Archivo:** [`dashboard/src/Chats.jsx`](dashboard/src/Chats.jsx)
- **Qué hacer:** si el tenant no tiene `phone_number_id`, mostrar una tarjeta
  **"Conectá tu WhatsApp (próximamente)"** deshabilitada. Sin lógica de conexión todavía
  (eso es Fase 5). Dejar el componente preparado para enchufar el botón de Embedded Signup.
- **Aceptación:** tenant sin WhatsApp ve el placeholder; con WhatsApp ve los chats normales.

### ▶ Cierre Fase 4
- **Skill ECC:** `ecc:security-review` (aislamiento entre tenants en `/admin/*`).

---

## FASE 5 — Embedded Signup de Meta (cuando Meta apruebe)

> Solo arrancar cuando la Tarea 0.1 esté **aprobada**. Hasta entonces queda el placeholder.

### Tarea 5.1 — Backend: intercambio del code
- **Skill ECC:** `ecc:backend-patterns` + `ecc:security-review` + `ecc:documentation-lookup` (Meta Embedded Signup)
- **Archivo nuevo:** `app/api/routes/wa_onboarding.py` · registrar en `main.py`
- **Endpoints:**
  - `GET /wa/embedded-config` (auth) → `app_id` + `config_id` para el SDK.
  - `POST /wa/embedded-exchange` (auth) → recibe `code`, intercambia por token de negocio,
    obtiene `waba_id` + `phone_number_id`, registra el número, suscribe la app a los webhooks
    del WABA, **cifra el token** con [`app/core/crypto.py`](app/core/crypto.py) y lo guarda en
    `tenants`. Llama `bust_tenant_cache()` de
    [`app/services/tenant_service.py`](app/services/tenant_service.py:30).
- **Aceptación:** tras el flujo, el tenant tiene `phone_number_id` + token cifrado y el webhook
  rutea sus mensajes (la resolución por `phone_number_id` ya existe).

### Tarea 5.2 — Frontend: botón Embedded Signup
- **Skill ECC:** `ecc:frontend-patterns` + `ecc:documentation-lookup`
- **Archivo:** [`dashboard/src/Chats.jsx`](dashboard/src/Chats.jsx) (reemplaza el placeholder)
- **Qué hacer:** cargar el JS SDK de Meta, lanzar `FB.login` con `config_id`, capturar el `code`
  del evento y mandarlo a `POST /wa/embedded-exchange`. Estados de carga/éxito/error.
- **Aceptación:** una inmobiliaria conecta su WhatsApp sola, sin intervención del owner.

### Tarea 5.3 — Verificación de firma del webhook de Meta
- **Skill ECC:** `ecc:security-review`
- **Archivo:** [`app/api/routes/webhook.py`](app/api/routes/webhook.py)
- **Qué hacer:** validar `X-Hub-Signature-256` con `META_APP_SECRET` en el webhook inbound
  (si no está ya). Rechazar firmas inválidas.
- **Aceptación:** payload con firma inválida → 403.

### ▶ Cierre Fase 5
- **Skill ECC:** `ecc:security-review` + `ecc:e2e-testing` (flujo conexión → mensaje real).

---

## FASE 6 — Pulido / hardening / E2E

### Tarea 6.1 — Límites por plan
- **Skill ECC:** `ecc:backend-patterns`
- **Qué hacer:** si hay tiers, enforcement de límites (ej: nº de propiedades) según `plan`.
- **Aceptación:** exceder el límite del plan da error claro.

### Tarea 6.2 — Panel super-admin
- **Skill ECC:** `ecc:frontend-patterns` + `ecc:backend-patterns`
- **Qué hacer:** vista (gated por `role=superadmin` + `x-api-key`) para listar tenants,
  estados de suscripción y, provisionalmente, setear `phone_number_id` a mano si hiciera falta.
- **Aceptación:** el owner ve todos los tenants; un tenant normal no accede.

### Tarea 6.3 — Suite E2E
- **Skill ECC:** `ecc:e2e-testing`
- **Qué hacer:** flujo completo signup → trial → checkout → dashboard → (Fase 5) conexión WA.
- **Verificación:** la suite E2E pasa contra staging.

### ▶ Cierre del proyecto
- **Skill ECC:** `ecc:security-review` (auditoría final: JWT en cookies httpOnly, firmas de
  webhooks MP+Meta, `SECRET_KEY` rotado, tokens cifrados, aislamiento RLS) + `ecc:verification-loop`.

---

## Apéndice A — Modelo de datos nuevo (resumen)

| Tabla | Propósito | Scope |
|---|---|---|
| `tenant_accounts` | Login de la inmobiliaria (email/password/role) | Global (no RLS) |
| `subscriptions` | Estado de pago MercadoPago por tenant | Global (no RLS) |
| `tenants` (existe) | + se usan `status`, `plan`, `waba_id`, `phone_number_id`, `wa_access_token` | — |

## Apéndice B — Endpoints nuevos (resumen)

```
POST /auth/signup · /auth/login · /auth/refresh · /auth/forgot-password · /auth/reset-password
GET  /auth/me · /auth/verify-email
POST /billing/subscribe · /webhooks/mercadopago
GET  /billing/status
GET  /wa/embedded-config            (Fase 5)
POST /wa/embedded-exchange          (Fase 5)
```

## Apéndice C — Checklist de seguridad (correr `ecc:security-review` al cierre de cada fase)

- [ ] `SECRET_KEY` ≠ default; rotado en Render.
- [ ] JWT en cookie **httpOnly + Secure + SameSite**, no en localStorage.
- [ ] Passwords con argon2/bcrypt (nunca plano).
- [ ] Firma del webhook MercadoPago validada.
- [ ] Firma `X-Hub-Signature-256` de Meta validada.
- [ ] Tokens de WhatsApp **cifrados** (Fernet) en reposo.
- [ ] Aislamiento entre tenants verificado (RLS activo en cada ruta de tenant).
- [ ] `x-api-key` solo para super-admin; resto migrado a JWT.
- [ ] Rate-limiting en `/auth/*` (anti fuerza bruta).

## Apéndice D — Riesgos / orden de ataque

1. **Meta Tech Provider** es el cuello de botella (semanas) → Tarea 0.1 desde el día 1; el SaaS
   se construye y se prueba sin clientes hasta tener la aprobación.
2. **`SECRET_KEY` default** → cambiar antes de cualquier JWT en prod.
3. **Aislamiento de tenants** (Tarea 1.5) es el punto más crítico de seguridad: testear que un
   tenant nunca ve datos de otro antes de exponer nada.
4. **Idempotencia de webhooks** (MP puede reenviar): no duplicar cobros/estados.
```
