---
id: 23
title: "Configuración cleanup — quitar 'Sistema' (v3 router por defecto) + dedupe 'Equipo'"
status: completed
priority: medium
area: frontend+backend
files:
  - dashboard/src/Config.jsx        # sección Sistema (router) + Equipo
  - dashboard/src/Shell.jsx         # nav (posible doble Equipo)
  - app/api/routes/admin.py         # tenant settings / active_router
  - app/db/models/tenant.py         # tenant_settings.active_router
  - app/core/router.py              # selección de router
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  sistema: "quitar la sección Sistema de la UI; hardcodear v3 como router por defecto para todos"
  equipo: "dejar solo Configuración/Equipo; eliminar la duplicada"
skills: ["react-patterns", "fastapi-patterns", "python-testing"]
agents: ["react-reviewer", "security-reviewer"]
---

# Plan 23 — Cleanup de Configuración (Sistema + Equipo)

## 1. Objetivo
(a) **Quitar la sección "Sistema"** (elección de router v1/v2/v3): no es decisión del usuario → **hardcodear v3 como router por defecto** para todos. (b) **Deduplicar "Equipo"**: hoy hay dos (una en Sistema y otra en Configuración/Equipo) → dejar **solo Configuración/Equipo**.

## 2. Contexto necesario (estado actual real)
- `Config.jsx` tiene `RouterSegmented`/`TenantRouterSwitch` (selección v1/v2/v3 vía `active_router`/`useUpdateTenantSettings`). El router efectivo lo resuelve `app/core/router.py` + `tenant_settings.active_router`.
- Hay **doble "Equipo"** (una bajo Sistema/superadmin y otra en Configuración/Equipo).
- v3 ya existe (router multi-tenant; en planes previos hacía fallback a V2). Decisión: **v3 default global**.

## 3. Plan secuencial
- [ ] **Backend — v3 default**: que el router por defecto sea **v3** para todos los tenants sin tener que setear `active_router` (default en `router.py`/settings). No exponer el switch. Conservar `active_router` en DB por compat, pero ignorar/forzar v3 si se decide; documentar. Tests: un tenant sin config usa v3.
- [ ] **Frontend — quitar Sistema**: eliminar la sección/nav "Sistema" (router) de Config y del menú. Quitar `RouterSegmented`/`TenantRouterSwitch` (código muerto) sin romper imports.
- [ ] **Dedupe Equipo**: eliminar la pestaña "Equipo" duplicada (la de Sistema); dejar solo `Configuración/Equipo` (la conectada a `team.py`). Verificar que el nav no muestre dos.
- [ ] Asegurar que quitar Sistema no rompa rutas/`VIEW_TO_PATH` ni el gating.

## 4. Criterios de aceptación
- No existe la sección Sistema ni el selector de router en la UI; el bot usa v3 por defecto.
- Hay una sola pestaña Equipo (Configuración/Equipo) funcionando.
- Sin código muerto del router-switch; build verde.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer** (remover sin romper nav/imports), **security-reviewer** (que forzar v3 no afecte aislamiento).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar (ideal para detectar código muerto); **Chrome MCP/Playwright en Docker** (light+dark).

## 6. Verificación
- `pytest` (default v3); `npm run build`.
- Chrome MCP/Playwright: Config sin Sistema, un solo Equipo.
- `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Decisiones: quitar Sistema + v3 default; Equipo único en Configuración/Equipo.
- 2026-06-20 — Implementado. SectionSistema + ROUTER_OPTIONS + ícono + nav/search entry removidos (~70 líneas). _resolve_active_router() hardcodeado a 'v3'. No había Equipo duplicado (confirmado por react-reviewer). Build OK, react-reviewer APPROVE. SHA: 960bcca.
