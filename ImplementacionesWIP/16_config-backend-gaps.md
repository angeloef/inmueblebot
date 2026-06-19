---
id: 16
title: "Configuración — huecos de backend que el nuevo layout necesita"
status: pending
priority: high
area: backend
files:
  - app/api/routes/auth.py          # /me (274), reset (token); FALTA change-password autenticado + update perfil
  - app/services/auth_service.py    # hash_password/authenticate → reusar para change-password
  - app/api/routes/team.py          # settings del dueño / o nuevo endpoint self-settings
  - app/api/routes/org.py           # update display_name/business_hours pero gated a require_org (solo orgs)
  - app/db/models/tenant.py         # display_name/company_name/business_hours/timezone (ya existen)
  - app/db/models/tenant_account.py # full_name, password_hash, extra_data (avatar color)
  - app/api/routes/                 # nuevo endpoint de uso por tenant (Uso)
depends_on: []
note: "Base del plan 17 (UI). El layout edita perfil, contraseña, datos de la inmobiliaria y muestra uso."
skills: ["fastapi-patterns", "python-patterns", "python-testing"]
agents: ["Plan", "security-reviewer"]
---

# Plan 16 — Backend: huecos para Configuración

## 1. Objetivo
Construir los endpoints que el nuevo layout de Configuración necesita y **hoy no existen**, para que el plan 17 (UI) los cablee. Lo demás del diseño ya tiene backend (facturación = planes 08/09, equipo = `team.py`, router = `tenant_settings.active_router`, inmobiliarias = `admin/tenants`, email-verified/login-methods = `/auth/me`).

## 2. Contexto necesario (estado actual real)
- **Ya existe (no construir):** `/auth/me` (`auth.py:274`) expone `full_name`, `email`, `email_verified`, `auth_methods` (password/google), `tier/limits/features` (plan 08), branches, subscription. Logout/refresh OK. Tenant model (`tenant.py`) ya tiene `display_name`, `company_name`, `business_hours` (horario), `timezone`.
- **Huecos confirmados:**
  1. **Cambio de contraseña autenticado** — `auth.py` solo tiene reset por token (forgot). No hay "cambiar contraseña estando logueado" (actual + nueva). `auth_service` tiene `hash_password`/`authenticate` a reusar.
  2. **Update del propio perfil** — no hay PATCH para `full_name` (el diseño lo edita en "General"). Tampoco para el **color de avatar** (preferencia nueva → guardar en `tenant_account.extra_data`).
  3. **Settings del dueño (no superadmin, no-org)** — `org.py` permite editar `display_name`/`business_hours` pero **gated a `require_org`** (solo orgs Enterprise). El PATCH de tenant settings en `admin.py` es `require_superadmin`. Falta una vía **self-service** para que el dueño de una inmobiliaria standalone edite **su** `display_name`, `company_name`, `business_hours`, `timezone` y `agent_whatsapp`. (Confirmar si `Config.jsx`/`useUpdateTenantSettings` ya pega a algo apto; si es superadmin-only, agregar el self endpoint.)
  4. **Uso por tenant** — la sección "Uso" necesita conteos del tenant actual: **propiedades** (count), **conversaciones del mes** (count sobre `conversations`/`messages` del período), **miembros del equipo** (count). Hoy los counts existen a nivel global (admin_analytics) pero **no** hay endpoint de uso del propio tenant. Los **límites** ya salen de `me.limits` (plan 08).

## 3. Plan secuencial
> Arrancar con **Plan** para fijar contratos (rutas/schemas) y evitar duplicar settings.

- [ ] **`POST /auth/change-password`** (autenticado): body `{current_password, new_password}` (min 8). Verifica la actual con `authenticate`/hash, setea la nueva, invalida sesiones si corresponde. Rechaza si la cuenta es solo-Google (sin password) con mensaje claro. Rate-limit.
- [ ] **`PATCH /auth/me`** (o `/auth/profile`): actualiza `full_name` y `avatar_color` (en `extra_data`, validar contra el set del diseño: navy/teal/violet/green). Devuelve el `me` actualizado.
- [ ] **Self-settings de la inmobiliaria**: endpoint para que el dueño/admin del tenant edite `display_name`, `company_name`, `business_hours`, `timezone`, `agent_whatsapp` de **su** tenant (gated a owner/admin del propio tenant, no superadmin). Reusar lógica existente; **no** permitir tocar otro tenant. (Si ya existe vía `team.py`/`useUpdateTenantSettings`, solo documentarlo y completá los campos faltantes.)
- [ ] **`GET /usage`** (tenant-scoped): `{ properties:{used,limit}, conversations_month:{used,limit}, team_members:{used,limit} }`. `used` = counts del tenant (propiedades, conversaciones del mes actual, miembros); `limit` desde el catálogo de plan (plan 08). Cachear si es caro.
- [ ] **Estado WhatsApp (derivado)** — exponer en `/auth/me` o en self-settings un `whatsapp_status` ('connected'|'pending') derivado de si el tenant tiene `phone_number_id`/token. (La conexión real "Conectar WhatsApp" NO se construye acá — es placeholder en el plan 17, embedded signup en un plan futuro.)
- [ ] **Tests** pytest: change-password (ok, contraseña actual incorrecta → 400/401, cuenta google-only → 409); PATCH perfil (valida color); self-settings (no puede editar otro tenant → 403); `/usage` (counts correctos + límites del plan); todo tenant-scoped.

## 4. Criterios de aceptación
- El dueño puede cambiar su contraseña, editar su nombre/color de avatar y los datos de su inmobiliaria (nombre, horario, zona horaria, WhatsApp del agente) desde su propia sesión, sin tocar datos de otros tenants.
- `GET /usage` devuelve uso vs límite para propiedades, conversaciones del mes y miembros.
- `me.whatsapp_status` refleja si el número está conectado.
- `security-reviewer` aprueba (no cross-tenant, verificación de contraseña actual, validación de inputs, rate-limit en password).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns` (schemas/deps/validación), `python-patterns`, `python-testing`.
- **Agentes:** **Plan** (contratos antes de codear; no duplicar settings), **security-reviewer** (password flow, tenant-scoping, rate-limit).
- **MCP:** ninguno.
- **Workflow:** contratos → endpoints + tests → exponer en `/me`/`/usage`. No tocar UI (plan 17).

## 6. Verificación
- `pytest` en Docker (password/perfil/self-settings/usage/scoping); `ruff`/`black`.
- Smoke: change-password con clave incorrecta → error claro; `/usage` cuadra con queries directas.
- `security-reviewer` sobre auth/self-settings/usage.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado a partir del handoff "Claude interface layout". Huecos confirmados leyendo auth.py/org.py/team.py/tenant.py: change-password autenticado, PATCH perfil, self-settings del dueño, GET /usage, whatsapp_status derivado. WhatsApp embedded signup queda fuera (placeholder en 17).
