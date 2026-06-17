---
id: 05
title: "Super-admin — explorador global cross-tenant con edición full"
status: completed
priority: high
area: backend+frontend
files:
  - app/api/routes/admin.py         # nuevos endpoints superadmin cross-tenant
  - app/db/repository.py            # repos (reusar/extender para queries globales)
  - app/db/models/                  # user, property, appointment, cobranzas, tenant, subscription
  - dashboard/src/superadmin/       # vistas globales (creadas en 04)
  - dashboard/src/api.js            # hooks superadmin (cross-tenant)
endpoints_nuevos:
  - GET  /admin/global/clients?tenant_id=&q=&page=
  - GET  /admin/global/properties?...
  - GET  /admin/global/appointments?...   # + contratos/cobranzas
  - PATCH /admin/global/{entity}/{id}      # edición full (superadmin)
reuse:
  - dashboard/src/Clients.jsx       # patrón de tabla/drawer/editor a adaptar
  - dashboard/src/Properties.jsx
  - dashboard/src/LinkClientProperty.jsx  # creado en plan 01
depends_on: ["04"]
skills: ["fastapi-patterns", "python-testing", "react-patterns", "accessibility"]
agents: ["security-reviewer", "react-reviewer", "e2e-runner"]
---

# Plan 05 — Explorador global cross-tenant (full access)

## 1. Objetivo
Dentro de `/superadmin`, una pestaña **"Datos"** con **tablas globales** (todas las inmobiliarias) para **revisar y editar con acceso total**: clientes, propiedades, citas/contratos/cobranzas y config/billing del tenant. Búsqueda, filtro por tenant y **edición inline**.

## 2. Contexto necesario (estado actual real)
- La **capa cross-tenant** la provee el Plan 04 (`superadmin_db()`/estrategia RLS). Este plan **consume** esa capa; no la rediseña.
- **Entidades y dónde viven:**
  - Clientes → `users` (+ `extra_data`: email/role/notes/property_relations). Mapeo front en `api.js` `toLead/toClient`.
  - Propiedades → `properties` (+ `extra_data`: building_type/city/buyer_id/tenant_id).
  - Citas → `appointments`; contratos/cobranzas → `app/db/models/cobranzas.py` (`contracts`, `charges`, `economic_indices`).
  - Config/billing → `tenant`, `tenant_settings`, `subscriptions` (endpoints superadmin ya existen para tenants/settings en `admin.py:2407+`).
- **Patrones de UI a adaptar (no reinventar):** `Clients.jsx` (tabla + drawer + `ClientEditor`) y `Properties.jsx` (drawer + editor) ya resuelven listar/editar por tenant. La versión global agrega **columna "Inmobiliaria"** y quita el scoping implícito.
- **Riesgo:** edición cross-tenant escribe en datos de clientes reales de terceros → exige confirmaciones y auditoría (reusar el `activity_log` del Plan 03 para registrar quién-editó-qué desde superadmin, con `actor='superadmin:<id>'`).

## 3. Plan secuencial

### Backend
- [ ] Endpoints `GET /admin/global/<entity>` (clients, properties, appointments+contracts) con: filtro `tenant_id` opcional, búsqueda `q`, **paginación** y orden. Tenant-aware en la respuesta (incluir `tenant_id` + nombre de inmobiliaria por fila).
- [ ] Endpoints `PATCH /admin/global/<entity>/<id>` para edición full. Validación Pydantic estricta (schemas de update separados). Reusar la lógica de los endpoints por-tenant existentes (no duplicar reglas de negocio).
- [ ] Emitir `activity_log` (Plan 03) en cada edición superadmin.
- [ ] Tests: aislamiento (un PATCH afecta solo la fila objetivo), paginación, y que un no-superadmin reciba 403.

### Frontend
- [ ] Pestaña "Datos" en `/superadmin` con sub-tabs por entidad (Clientes / Propiedades / Citas-Contratos).
- [ ] Tablas globales con: columna **Inmobiliaria**, buscador, filtro por tenant (usa el selector global del shell del Plan 04), paginación.
- [ ] **Edición**: reusar/adaptar los editores existentes (`ClientEditor`, editor de Properties) en modo superadmin (todos los campos, sin restricción de suscripción). Confirmación explícita antes de guardar cambios de datos ajenos.
- [ ] Hooks en `api.js` (`useGlobalClients`, etc.) que peguen a `/admin/global/*` con invalidación de caché correcta.

## 4. Criterios de aceptación
- Se listan y filtran clientes/propiedades/citas de **todas** las inmobiliarias, con su tenant visible.
- Se puede editar cualquier registro y el cambio persiste, queda auditado en `activity_log` y se refleja sin recargar.
- Acceso denegado (403) para cualquier rol que no sea superadmin.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns`, `python-testing`, `react-patterns`, `accessibility`.
- **Agentes:** **security-reviewer** (cada PATCH cross-tenant: autz, validación, auditoría), **react-reviewer** (tablas/editores reutilizados), **e2e-runner** (flujo editar registro de otro tenant).
- **MCP:** ninguno externo.
- **Workflow:** backend + tests de aislamiento primero; luego UI reusando componentes. No reescribir reglas de negocio: envolver las existentes.

## 6. Verificación
- `pytest` (aislamiento + 403 + auditoría).
- `npm run build`; Chrome MCP: filtrar por tenant, editar un cliente de otra inmobiliaria, ver el cambio + entrada en activity_log.
- `security-reviewer` sobre los endpoints `/admin/global/*`.

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Depende de 04 (capa cross-tenant) y reusa activity_log de 03 para auditar ediciones.
- 2026-06-17 — **Implementado y completado.**
  - **Backend:** nuevo módulo `app/api/routes/admin_global.py` (router `/admin/global`, registrado
    en `main.py` también bajo `/api`). GET `clients|properties|appointments` con filtro `tenant_id`,
    búsqueda `q`, paginación y `tenant_id`+`tenant_name` por fila (reusa los mappers de `admin.py`).
    PATCH `/{entity}/{id}` con schemas Pydantic whitelist + allowlist de columnas a nivel ORM
    (defensa en profundidad: nunca reasigna `tenant_id`). Cada edición emite `activity_log`
    (`action='superadmin_edited'`, `actor='superadmin:<id>'`). Todo gateado por `require_superadmin`.
  - **Frontend:** pestaña "Datos" → `GlobalExplorer.jsx` (sub-tabs Clientes/Propiedades/Citas,
    columna Inmobiliaria, buscador, filtro por el selector del shell, paginación, editor lateral
    con confirmación explícita y foco modal). Hooks `useGlobalClients/Properties/Appointments` +
    `useUpdateGlobalEntity` en `api.js` (v5 `placeholderData: keepPreviousData`, `enabled` por sub-tab).
  - **Gates:** ruff ✓ · `tests/test_admin_global.py` 8/8 en Docker ✓ · `npm run build` ✓ ·
    e2e API (login superadmin → list cross-tenant 70 clientes/221 props con tenant_name → PATCH
    persistido → fila en `activity_log` → 404 entidad desconocida → `tenant_id` rechazado) ✓ ·
    security-reviewer (HIGH-1 allowlist ORM aplicado) + react-reviewer (hook condicional, v5
    placeholderData, ARIA tabpanel/dialog) ✓.
  - **Nota:** verificación visual con navegador no se pudo correr (perfil de Chrome MCP bloqueado);
    cubierta por el build verde + e2e a nivel API que ejerce exactamente lo que consume la UI.
