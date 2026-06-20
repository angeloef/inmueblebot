---
id: 27
title: "Cuenta — borrar cuenta con 2FA por email + advertencias (irreversible)"
status: completed
priority: high
area: backend+frontend
files:
  - dashboard/src/Config.jsx        # Cuenta → nueva acción 'Borrar cuenta'
  - app/api/routes/auth.py          # endpoints solicitar/confirmar borrado
  - app/services/email_service.py   # envío del código 2FA (reusa _send)
  - app/db/models/                  # tenant_account / cascada de borrado
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
skills: ["fastapi-patterns", "python-testing", "react-patterns", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 27 — Borrar cuenta con 2FA por email

## 1. Objetivo
En Configuración → Cuenta, agregar **borrar la cuenta** con **2FA por correo** (código de confirmación), **advertencias claras** de que es **irreversible** y borra **todos los datos** sin recuperación.

## 2. Contexto necesario (estado actual real)
- No existe flujo de borrado de cuenta. `email_service` ya envía correos (reusar para el código). Auth maneja cuentas (`tenant_account`).
- **Cuidado**: borrar una cuenta puede implicar borrar/huérfanos de un tenant entero (propiedades, clientes, contratos, etc.). Definir el **alcance** del borrado (cuenta vs tenant) y la **cascada** con el subagente Plan + security-reviewer. Para un dueño único, probablemente borra el tenant y sus datos; para un miembro, solo su acceso.

## 3. Plan secuencial
> Arrancar con **Plan**/security-reviewer para definir alcance del borrado y cascada (cuenta vs tenant, qué pasa con sucursales/datos).
- [ ] **Backend — solicitar borrado**: `POST /auth/account/delete/request` (autenticado) → genera un **código 2FA** de un solo uso (TTL corto), lo envía por email, lo guarda hasheado. Rate-limit.
- [ ] **Backend — confirmar borrado**: `POST /auth/account/delete/confirm` con el código → valida, ejecuta el borrado definitivo (cascada definida), cierra sesión. Auditar (log). Tests: código inválido/expirado → error; borrado correcto; scoping (no borrar otra cuenta/tenant).
- [ ] **Frontend**: en Cuenta, sección de peligro con botón "Borrar cuenta" → modal con **advertencias** (irreversible, borra todo) + paso de **confirmación por código** enviado al email + (opcional) escribir el nombre/EMAIL para confirmar. Estados de carga/erro; al completar, logout + mensaje.

## 4. Criterios de aceptación
- El borrado requiere código 2FA enviado al email del titular; muestra advertencias claras de irreversibilidad.
- Tras confirmar, los datos se borran según el alcance definido y la sesión se cierra.
- No se puede borrar otra cuenta/tenant; código expira/uso único.
- `security-reviewer` aprueba (2FA, rate-limit, cascada, auditoría).

## 5. Skills / MCP / Workflow AI
- **Agentes:** **Plan** (alcance + cascada), **security-reviewer** (2FA/borrado/aislamiento), **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (flujo completo, light+dark) — en test, mockear/loguear el código.

## 6. Verificación
- `pytest` (request/confirm, código inválido/expirado, scoping, cascada) en Docker; `ruff`/`black`; `npm run build`.
- Chrome MCP/Playwright: flujo de borrado con código (mock) y advertencias.
- `security-reviewer` (crítico).

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Definir alcance del borrado (cuenta vs tenant) y cascada en preflight con Plan + security-reviewer. 2FA por email reusando email_service.
- 2026-06-20 — Implementado. Backend: POST /auth/account/delete/request (código 6 dígitos SHA-256 en Redis, TTL 15min, rate-limit 3/h, email via email_service) + POST /auth/account/delete/confirm (owner solo→delete tenant cascade; owner con equipo/sucursales→409; member→delete account). Frontend: DeleteAccountModal 2-pasos (advertencias + código) en SectionCuenta zona de peligro. 3 tests (monkeypatched Redis). /ponytail full aplicado (func import en top-level, Tenant re-use, errores de línea larga corregidos). Build ✓. SHA: 8e2e7dd.
