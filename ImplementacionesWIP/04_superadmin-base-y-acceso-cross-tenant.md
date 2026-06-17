---
id: 04
title: "Super-admin — base: ruta /superadmin + auth por role + acceso cross-tenant"
status: completed
priority: high
area: backend+frontend
files:
  - app/api/deps.py                 # require_superadmin (132-162) — base de auth
  - app/api/routes/auth.py          # login emite JWT con role (125)
  - app/db/tenant_session.py        # GUC app.current_tenant_id → RLS
  - app/db/session.py               # get_db
  - app/api/routes/admin.py         # endpoints superadmin existentes (2407+)
  - dashboard/src/main.jsx          # BrowserRouter + gate de sesión
  - dashboard/src/App.jsx           # VIEW_TO_PATH / routing
  - dashboard/src/auth.jsx          # AuthProvider/useAuth
endpoints_existentes:
  - GET/POST/PATCH/DELETE /admin/tenants*          # ya gateados por require_superadmin
  - POST /auth/login                               # JWT con role (superadmin soportado)
depends_on: []
note: "Foundation de los planes 05/06/07. No hard-dep de 01-03, pero conviene tras estabilizar 03."
skills: ["fastapi-patterns", "react-patterns", "accessibility"]
agents: ["Plan", "security-reviewer", "react-reviewer"]
---

# Plan 04 — Super-admin: base y acceso cross-tenant

## 1. Objetivo
Crear la **superficie aislada `/superadmin`** (ruta separada con su propio login, gateada por `role=superadmin`) para los 2 devs, y la **capa de acceso cross-tenant** del backend que permite leer/editar datos de **cualquier** inmobiliaria de forma segura. Es la base sobre la que se montan los planes 05 (explorador), 06 (analítica) y 07 (errores).

## 2. Contexto necesario (estado actual real)

**Auth ya soporta superadmin:**
- `app/api/deps.py:132-162` `require_superadmin`: acepta `ADMIN_API_KEY` global (ops, ve todo, sin tenant) **o** un JWT con `account.role == "superadmin"`. Fail-closed.
- `app/api/routes/auth.py:125` `login` emite `create_access_token(account.id, account.tenant_id, account.role)` y setea cookie httpOnly. Los 2 devs necesitan `TenantAccount` con `role='superadmin'`.
- Ya existen endpoints superadmin: CRUD de tenants y settings (`admin.py:2407+`).

**Multi-tenant / RLS (lo crítico):**
- `app/db/tenant_session.py`: un listener setea por transacción `set_config('app.current_tenant_id', <tid>, true)`. Las policies RLS filtran `tenant_id = current_setting('app.current_tenant_id', true)::uuid`.
- El path `ADMIN_API_KEY` yield `None` ("no resuelve tenant → ve todo"): **verificar exactamente cómo** se materializa ese "ve todo" (¿rol DB con BYPASSRLS? ¿policy para GUC vacío? ¿se itera por tenant?). **Este es el riesgo central del plan** → arrancar con subagente **Plan/Explore** sobre `app/db/` (session, tenant_session, base, repository) y las migraciones de policies en `alembic/versions/`.
- Decisión a tomar (documentar en bitácora): para queries cross-tenant del superadmin, elegir UNA estrategia consistente:
  1. **Bypass RLS** vía rol/conexión con BYPASSRLS solo en endpoints `require_superadmin`, o
  2. **Iterar por tenant** seteando el GUC (seguro pero N queries), o
  3. **Policy superadmin**: una RLS policy que permita ver todo cuando un GUC `app.is_superadmin='on'` está seteado.
  Recomendación inicial: opción 3 (explícita, auditable, sin tocar privilegios de rol), validar con `security-reviewer`.

**Frontend (SPA, fácil de extender):**
- `main.jsx`: `BrowserRouter` + gate de sesión (monta dashboard solo con JWT válido vía `GET /auth/me`).
- `App.jsx`: `VIEW_TO_PATH`/`PATH_TO_VIEW` mapean vistas↔rutas. `auth.jsx` expone `useAuth` (incluye `role`, confirmar).
- "Ruta/app separada" se implementa como **árbol de rutas `/superadmin/*` con su propio layout y gate** dentro del mismo SPA (no requiere otro deploy). Si más adelante se quiere separación dura, se extrae a otro bundle.

## 3. Plan secuencial

### Backend
- [ ] Confirmar/crear el mecanismo cross-tenant (ver §2, decidir estrategia con Plan/security-reviewer). Encapsular en un helper/dep `superadmin_db()` o `with_all_tenants(db)` reutilizable por 05/06/07.
- [ ] Endpoint `GET /admin/me` o extender `/auth/me` para exponer `role` (el front lo usa para gatear `/superadmin`).
- [ ] Asegurar que los 2 devs tengan cuentas `role='superadmin'` (script/seed o doc en `TEST_USERS.md`).

### Frontend
- [ ] Árbol de rutas `/superadmin` con layout propio (`dashboard/src/superadmin/SuperadminApp.jsx` + shell). Reusar `Primitives.jsx`/tokens.
- [ ] **Gate por role**: si no hay JWT → login propio (reusar `POST /auth/login`); si hay JWT pero `role!=='superadmin'` → 403/redirect. Nunca renderizar la UI superadmin a un no-superadmin (defensa en profundidad: el backend ya es fail-closed).
- [ ] Shell con navegación de pestañas vacías (placeholders) que llenarán 05/06/07: "Datos", "Analítica", "Errores".
- [ ] Selector global de tenant (dropdown que lista `/admin/tenants`) en el header del shell — estado compartido para que 05/06 lo consuman.

## 4. Criterios de aceptación
- `/superadmin` solo accesible con `role=superadmin`; un usuario normal recibe 403 tanto en UI como en API.
- El backend puede listar entidades de ≥2 tenants distintos en una sola request superadmin (probado con datos de 2 tenants), sin filtrarse a usuarios no-superadmin (RLS sigue activa para el resto).
- `security-reviewer` aprueba la estrategia cross-tenant (sin agujeros de aislamiento).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns` (deps/sec), `react-patterns`, `accessibility`.
- **Agentes:** **Plan** (diseñar estrategia RLS/cross-tenant ANTES de codear), **security-reviewer** (aislamiento de tenants, fail-closed, no leak de PII), **react-reviewer** (gate y routing).
- **MCP:** ninguno externo.
- **Workflow:** plan de mayor riesgo de seguridad → diseño primero, tests de aislamiento antes que UI. Usar **Explore** para mapear `app/db/` y las policies en `alembic/versions/`.

## 6. Verificación
- `pytest` con tests de aislamiento: superadmin ve N tenants; rol normal sigue viendo solo el suyo (RLS intacta); no-superadmin → 403.
- `ruff`/`black`; `npm run build`.
- Chrome MCP: login superadmin → `/superadmin` carga shell; login normal → 403/redirect.
- `security-reviewer` sobre el diff backend.

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Decisión pendiente: estrategia exacta de acceso cross-tenant (bypass vs GUC superadmin vs iterar). Resolver con Plan + security-reviewer en preflight.
- 2026-06-16 — Inicio implementación (implementador-loop). **Decisión cross-tenant: opción 3 (GUC superadmin)**. Mapeo del estado real:
  - RLS usa `FORCE ROW LEVEL SECURITY` + políticas org-aware (0002/0013): `col = GUC OR col IN (hijos del GUC)`. El path `ADMIN_API_KEY` NO ve todo hoy: el listener cae al default-tenant vía `resolve_tenant_id()`. Latent bug que esta opción corrige.
  - Estrategia: ContextVar `_superadmin` → el listener `after_begin` setea `app.is_superadmin` (transaction-local, `true`) → cada política RLS agrega `current_setting('app.is_superadmin', true) = 'on' OR ...`. Auditable, fail-closed (NULL-safe), sin tocar roles DB ni BYPASSRLS. Migración 0018 reescribe las 14 políticas con downgrade a la forma org-aware.
  - `require_superadmin` (ambos paths) activa el contexto superadmin → "ve todo" real, gateado fail-closed. Reusable por 05/06/07 vía `superadmin_scope()`.
  - `/auth/me` YA expone `role` (auth.py:318) → subtarea backend cumplida sin cambios.
- 2026-06-16 — **Implementado y verificado (5 gates verdes).**
  - Backend: `tenancy.py` (ContextVar `_superadmin` + `set/reset/is_superadmin_context`, GUC `SUPERADMIN_GUC`), `tenant_session.py` (listener escribe `app.is_superadmin` 'on'/'off' por transacción), `deps.py` (`require_superadmin` activa el contexto en ambos paths), migración `0018` (reescribe 16 políticas RLS con cláusula superadmin; up/down/up limpio en tablas reales). Seed reusable `scripts/seed_superadmin.py` (idempotente, crea/promueve superadmin; cubre "2 devs con role='superadmin'").
  - Frontend: árbol `/superadmin` aislado (`dashboard/src/superadmin/`): `SuperadminApp` (gate loading/anon/403/superadmin), `SuperadminLogin` (reusa `useAuth().login`), `SuperadminShell` (header + selector global de tenant + tabs Datos/Analítica/Errores placeholders), `TenantContext` (estado compartido para 05/06). `main.jsx` ramifica el path por `useLocation()`.
  - Gates: ruff ✓ · pytest 7/7 (3 nuevos tests de aislamiento superadmin + 4 existentes) ✓ · alembic up/down/up ✓ · vite build ✓ · Playwright UX (anon→login propio, superadmin→shell con 300+ tenants cross-tenant, no-superadmin→403, tabs) ✓.
  - **Reviews:** security-reviewer (cross-tenant) + react-reviewer. Resueltos: C1 (rechazar `ADMIN_API_KEY` default/inseguro en `require_superadmin` — mi cambio elevaba su blast radius a cross-tenant), C2 (eliminado `superadmin_scope` público no-guardado; 05/06/07 obtienen cross-tenant solo vía la dep `require_superadmin`), H2 (seed exige passphrase ≥12). H1 (excepción del GUC tragada) verificado **no explotable**: `set_config(...,true)` es transaction-local ⇒ un `'on'` nunca sobrevive su transacción aunque el listener falle. H3 (auto-promoción de role) descartado por inspección (no hay endpoint que escriba `tenant_accounts.role`). **Estrategia cross-tenant aprobada (opción 3, GUC superadmin).**
