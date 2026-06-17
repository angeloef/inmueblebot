---
id: 07
title: "Reporte de errores in-app + pestaña de triage en super-admin"
status: completed
priority: medium
area: backend+frontend
files:
  - app/db/models/                  # nuevo error_report.py
  - alembic/versions/               # migración tabla error_reports
  - app/api/routes/admin.py         # POST crear reporte + GET/PATCH triage superadmin
  - dashboard/src/Shell.jsx         # botón global "Reportar error"
  - dashboard/src/Primitives.jsx    # (posible) modal/IconButton reutilizable
  - dashboard/src/superadmin/       # nueva pestaña "Errores"
  - dashboard/src/api.js            # hooks reporte/triage
depends_on: ["04"]
skills: ["fastapi-patterns", "python-testing", "react-patterns", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 07 — Reporte de errores in-app + pestaña super-admin

## 1. Objetivo
Un **botón "Reportar error"** accesible desde la app (dashboard de inmobiliarias) que abre un modal para describir el problema, y una **pestaña "Errores"** en `/superadmin` donde los 2 devs ven, filtran y gestionan (triage) todos los reportes.

## 2. Contexto necesario (estado actual real)
- **No existe** modelo ni endpoint de error reports. Se crea nuevo.
- **Dónde poner el botón:** `Shell.jsx` envuelve la navegación del dashboard → es el lugar natural para un botón/acción global persistente (esquina o menú de usuario). Reusar `Button`/`IconButton`/modal de `Primitives.jsx`.
- **Contexto útil a capturar automáticamente** (para que el reporte sirva al dev): tenant_id + nombre, account_id/email del que reporta, ruta/vista actual (`location.pathname`), `version` (ya hay `version.js`/`startVersionWatcher` y endpoint `/version`), user-agent, y errores recientes de consola si están disponibles. **No** capturar datos sensibles (tokens/cookies) — filtrar.
- **Multi-tenant:** el reporte lo crea un usuario autenticado (no superadmin); la lectura/triage es superadmin (capa del Plan 04). La tabla es global (como `subscriptions`), con `tenant_id` para filtrar.

## 3. Plan secuencial

### Backend
- [ ] **Modelo** `app/db/models/error_report.py` → tabla `error_reports`:
  `id (uuid)`, `tenant_id (fk)`, `account_id (uuid, nullable)`, `reporter_email (str)`, `message (text)`, `context (JSONB: ruta, version, user_agent, console_tail)`, `severity ('low'|'med'|'high', default med)`, `status ('open'|'in_progress'|'resolved'|'wont_fix', default open)`, `created_at`, `updated_at`. Índice por `(status, created_at)`.
- [ ] **Migración alembic**.
- [ ] `POST /admin/error-reports` (auth normal, NO superadmin): crea el reporte. Validar/limitar tamaño; rate-limit básico; **redactar** cualquier credencial del `context`.
- [ ] `GET /admin/error-reports` + `PATCH /admin/error-reports/{id}` (superadmin): listar/filtrar por status/tenant/severity y actualizar status/severity/notas.
- [ ] Tests: creación por usuario normal, listado/triage solo superadmin (403 para el resto), redacción de secretos.

### Frontend
- [ ] **Botón "Reportar error"** global en `Shell.jsx` → abre modal (mensaje + severidad opcional). Auto-adjunta el `context` (ruta, version, UA). Accesible por teclado, foco atrapado (reusar patrón `useFocusTrap`).
- [ ] `useCreateErrorReport` en `api.js`; toast de éxito/error.
- [ ] **Pestaña "Errores"** en `/superadmin`: tabla con filtros (status/severity/tenant), detalle del `context`, y acciones de triage (cambiar status/severity, nota). Hooks `useErrorReports`/`useUpdateErrorReport`.
- [ ] (Opcional) badge con conteo de reportes `open` en el nav superadmin.

## 4. Criterios de aceptación
- Cualquier usuario autenticado puede enviar un reporte desde la app; queda persistido con contexto útil y sin datos sensibles.
- Los 2 devs ven y gestionan todos los reportes en `/superadmin`; no-superadmin no puede listar (403).
- El triage (cambio de status/severity) persiste y se refleja sin recargar.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns`, `python-testing`, `react-patterns`, `accessibility`.
- **Agentes:** **security-reviewer** (redacción de secretos en `context`, autz del POST vs GET, rate-limit), **react-reviewer** (modal/foco/teclado).
- **MCP:** ninguno externo.
- **Workflow:** modelo + endpoints + tests primero; luego botón global; luego pestaña de triage. Reusar primitivos de UI existentes.

## 6. Verificación
- `alembic upgrade head` + downgrade; `pytest` (autz + redacción).
- `npm run build`; Chrome MCP: enviar un reporte desde el dashboard → aparece en `/superadmin` con su contexto; cambiar status y verlo actualizado.
- `security-reviewer` sobre los endpoints y la redacción de `context`.

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Depende de 04 (lectura/triage es superadmin). El POST de creación usa auth normal, no superadmin.
- 2026-06-17 — Implementado y verificado. Backend: modelo `error_report.py` (tabla global `error_reports`, índice status+created_at) + migración `0019_error_reports` (upgrade/downgrade OK); `app/api/routes/error_reports.py` (NEW) con `POST /admin/error-reports` (auth normal: tenant_id/reporter_email del account, context redactado por nombre de clave + acotado en tamaño/profundidad), `GET` + `PATCH /admin/error-reports/{id}` (require_superadmin, 401 sin auth). Registrado en `main.py` (app + compat); `ErrorReport` exportado en `models/__init__.py`. Frontend: botón global "Reportar un error" + modal en `Shell.jsx` (useFocusTrap, adjunta context route/version/user_agent sin datos sensibles); pestaña "Errores" `ErrorTriage.jsx` (NEW) con filtros estado/gravedad (chips aria-pressed), tabla, drawer de triage (useFocusTrap, status/severity/notas, guardar deshabilitado sin cambios); hooks en `api.js`; wired en `SuperadminShell.jsx`. Gates: ruff OK; 8 tests (autz + redacción) verdes en Docker; migración up/down/up OK; `vite build` OK; Chrome MCP e2e (enviar reporte como usuario → aparece en /superadmin con context sanitizado → cambiar status a in_progress persiste), consola sin errores. Review security (APPROVE, solo LOW; documentada la limitación de redacción por nombre-de-clave) + react (3 HIGH de a11y resueltos: adoptado useFocusTrap en drawer, removido aria-hidden del backdrop del modal; + aria-pressed, staleTime, reset de página en handlers).
