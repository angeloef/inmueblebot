---
id: 15
title: "Importación asistida de propiedades — el cliente manda su listado, los devs lo cargan"
status: completed
priority: high
area: backend+frontend
files:
  - app/db/models/                       # nuevo property_import_request.py (+ archivos)
  - alembic/versions/                    # migración
  - app/api/routes/                      # nuevo property_imports.py (POST tenant + GET/PATCH superadmin)
  - app/services/email_service.py        # aviso al completar (reusa _send + reply_to, plan 12)
  - dashboard/src/Properties.jsx         # botón "Mandanos tu listado" (header + estado vacío del plan 14) + panel de estado
  - dashboard/src/api.js                 # hooks crear/listar import requests
  - dashboard/src/superadmin/SuperadminShell.jsx   # nueva pestaña "Importaciones"
  - dashboard/src/superadmin/            # nuevo PropertyImports.jsx (triage)
precedentes:
  - app/api/routes/error_reports.py      # patrón EXACTO tenant crea → superadmin gestiona (POST auth normal, GET/PATCH require_superadmin)
  - app/db/models/document.py            # archivos base64 en DB (size limit, content_type) → mismo patrón
  - dashboard/src/superadmin/ErrorTriage.jsx   # patrón de pestaña de triage a espejar
depends_on: ["14"]
decisiones:
  entrada: "subir archivos (Excel/CSV/PDF/Word/imágenes) + nota/contexto libre"
  seguimiento: "estado en la app (Recibido → En proceso → Cargadas) + email al cliente al completar"
  ubicacion_boton: "estado vacío (plan 14) + header de Propiedades"
skills: ["fastapi-patterns", "python-testing", "react-patterns", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 15 — Importación asistida de propiedades

## 1. Objetivo
Que una inmobiliaria con muchas propiedades **en otro formato** (planilla, PDF, fotos de listados) pueda **mandarnos su listado tal cual lo tiene** desde la app, sin cargarlas a mano. Los 2 devs lo reciben en una **pestaña nueva del super-admin**, lo parsean y lo suben en lote. El cliente ve el **estado** del pedido y recibe **email** cuando está listo.

> Pensado de punta a punta: **inicio** = el cliente (sobre todo con 0 propiedades) ve "¿Ya tenés tu cartera en otro lado? Mandánosla y la subimos por vos" → sube archivos + nota → confirma. **Resultado deseado** = los devs reciben el material, lo cargan en lote, marcan "Cargadas", y el cliente ve sus propiedades + recibe el aviso.

## 2. Contexto necesario (estado actual real)
- **Precedente directo en el repo** — `error_reports` (`app/api/routes/error_reports.py`): tenant **crea** con auth normal (`POST`, toma tenant/email del account), superadmin **lista/gestiona** (`GET`/`PATCH` con `require_superadmin`), tabla **global** con `tenant_id`, sanitización de contexto. **Espejar ese patrón** para los import requests.
- **Archivos** — `app/db/models/document.py`: archivo en **base64** en DB con `filename`, `content_type`, `size_bytes`, límite 5MB. Mismo patrón para los adjuntos del listado (un archivo puede ser pesado → definir límite y, si hace falta, varios archivos por request).
- **Superadmin** — `dashboard/src/superadmin/SuperadminShell.jsx` tiene tabs `data/analytics/errors` (líneas 18-20, render 127-129). Agregar `imports` espejando `ErrorTriage.jsx`.
- **Email** — `app/services/email_service.py` ya soporta `reply_to`/`send_*` (plan 12). Reusar para el aviso "tus propiedades ya están cargadas".
- **Estado vacío / header** — el botón se inserta en el onboarding del **plan 14** (0 propiedades) y en el header de Propiedades (junto a "Agregar propiedad").

## 3. Plan secuencial

### Backend
- [ ] **Modelo** `property_import_request.py` → tabla `property_import_requests`: `id (uuid)`, `tenant_id (fk)`, `account_id (uuid, nullable)`, `requester_email (str)`, `note (text)`, `status ('received'|'in_progress'|'completed'|'cancelled', default received)`, `item_count_estimate (int, nullable)`, `admin_notes (text, nullable)`, `created_at`, `updated_at`, `completed_at (nullable)`. Adjuntos: tabla hija `property_import_files` (o reusar/extender `documents` con un target nuevo) con `filename`, `content_type`, `size_bytes`, `data (base64)`. Índice `(status, created_at)`.
- [ ] **Migración alembic** (upgrade/downgrade).
- [ ] **Endpoints** (espejar error_reports):
  - `POST /admin/property-imports` (auth normal, tenant-scoped): crea request con `note` + archivos (validar tamaño/tipo/cantidad). Devuelve el request con estado `received`.
  - `GET /admin/property-imports` (auth normal): lista **los del propio tenant** (para el panel de estado del cliente).
  - `GET /admin/property-imports/all` + `PATCH /admin/property-imports/{id}` (**require_superadmin**): listar cross-tenant, descargar archivos, cambiar `status`/`admin_notes`. Descarga de archivo: endpoint dedicado tipo `documents` (stream inline).
  - Al pasar a `completed`: enviar **email** al `requester_email` vía `email_service` (reply-to inmobiliaria/plataforma).
- [ ] **Tests** pytest: crear como tenant; listar propio; superadmin lista todo y cambia estado; no-superadmin no accede al `/all` ni al PATCH (403); validación de archivos; email disparado al completar (mock).

### Frontend — cliente (Propiedades)
- [ ] **Botón "Mandanos tu listado y las subimos por vos"** en el header de Propiedades y, destacado, en el **estado vacío del plan 14**.
- [ ] **Modal/flujo de envío**: dropzone de archivos (reusar el patrón de fotos/documents) + textarea de nota/contexto ("¿cuántas son? ¿algo que debamos saber?") + submit con estado de carga. Copy que explique qué pasa después.
- [ ] **Panel de estado**: lista de pedidos del tenant con su estado (Recibido → En proceso → Cargadas) y fecha; visible en Propiedades (p. ej. una tarjeta/acordeón "Mis importaciones").
- [ ] Hooks en `api.js`: `useCreatePropertyImport`, `usePropertyImports` (propios). Invalidación + toasts.

### Frontend — super-admin (pestaña nueva)
- [ ] Tab **"Importaciones"** en `SuperadminShell.jsx` (espejar `ErrorTriage`): tabla cross-tenant (inmobiliaria, fecha, nota, nº archivos, estado), **descarga de archivos**, cambio de estado + notas internas, filtro por estado/tenant. Hooks `usePropertyImportsAll`/`useUpdatePropertyImport`.

## 4. Criterios de aceptación
- Desde Propiedades (header y onboarding de 0 props) el cliente sube archivos + nota y envía su listado; queda persistido con estado `received`.
- El cliente ve el estado de sus pedidos en la app y recibe **email** cuando pasan a `completed`.
- Los devs ven todos los pedidos en `/superadmin` → "Importaciones", descargan los archivos, y cambian el estado; no-superadmin recibe 403 en las rutas de gestión.
- Archivos validados (tipo/tamaño/cantidad); scoping por tenant correcto.
- `security-reviewer` aprueba (autz POST vs gestión superadmin, límites de archivo, sin leak cross-tenant).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns` (rutas/schemas/validación de archivos), `python-testing` (autz + email mock + scoping), `react-patterns`, `accessibility` (dropzone/modal/teclado/foco).
- **Agentes:** **security-reviewer** (subida de archivos: límites, content_type, autz; descarga solo superadmin; tenant-scoping), **react-reviewer** (dropzone, estados de carga, pestaña superadmin).
- **MCP:** ninguno externo.
- **Workflow:** **espejar `error_reports` (backend) y `ErrorTriage` (superadmin)** — patrón ya probado. Modelo + migración + endpoints + tests → flujo de envío cliente → panel de estado → pestaña superadmin. Reusar `documents` para archivos y `email_service` para el aviso.

## 6. Verificación
- `alembic upgrade head` + downgrade; `pytest` (crear/listar/triage/autz/archivos/email mock) en Docker; `ruff`/`black`.
- `npm run build`; **Chrome MCP**: como cliente con 0 propiedades → ver onboarding → "Mandanos tu listado" → subir archivo + nota → enviar → ver estado "Recibido"; como superadmin → pestaña Importaciones → ver el pedido, descargar archivo, marcar "Cargadas"; (si hay RESEND_API_KEY) verificar email, si no, el camino degradado. Screenshots + consola sin errores.
- `security-reviewer` sobre rutas y subida/descarga de archivos.

## 7. Bitácora (append-only)
- 2026-06-18 — Plan creado. Decisiones: entrada = archivos + nota; seguimiento = estado en app + email al completar; botón en estado vacío (plan 14) + header. Depende de 14 (estado vacío donde se inserta el CTA). Espeja error_reports + documents + ErrorTriage; reusa email_service (plan 12).
- 2026-06-18 — Implementado. Backend: PropertyImportRequest + PropertyImportFile (modelos), migración 0020, endpoints POST/GET-mine/GET-all/PATCH/GET-file. Frontend cliente: ImportModal (dropzone + nota), ImportStatusPanel, botón en header y estado vacío. Frontend superadmin: PropertyImports.jsx + pestaña en SuperadminShell. Gates: build ✓, ruff ✓, security-reviewer APPROVE (sin CRITICAL/HIGH). SHA: d7dc3d6. Pusheado a main → auto-deploy en Render (requiere alembic upgrade head post-deploy).
