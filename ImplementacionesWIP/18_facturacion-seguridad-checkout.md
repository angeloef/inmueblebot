---
id: 18
title: "Facturación — fix de seguridad crítico: el plan solo cambia con pago confirmado"
status: in_progress
priority: critical
area: backend+frontend
files:
  - dashboard/src/Config.jsx        # PlanSection (~327-472): botones 'Cambiar a Básico/Profesional'
  - dashboard/src/api.js            # useSubscribe / hooks billing
  - app/api/routes/billing.py       # subscribe (solo crea preapproval), webhook MP, billing_status
  - app/services/subscription_service.py  # sync_from_preapproval_id (única vía legítima de cambio)
depends_on: []
note: "OBLIGATORIO: tras implementar correr /ponytail full; verificación visual con Chrome MCP/Playwright en Docker local (light+dark)."
skills: ["fastapi-patterns", "react-patterns", "python-testing"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 18 — Facturación: seguridad crítica + checkout

## 1. Objetivo
Cerrar el **bug crítico**: hoy cualquier usuario logueado puede "cambiar" entre Básico y Profesional y el estado se refleja **sin pagar**. El plan debe cambiar **solo** cuando MercadoPago confirma el pago vinculado a esa cuenta. El checkout abre en **pestaña nueva** y la UI refleja el cambio recién cuando `billing/status` lo confirma.

## 2. Contexto necesario (estado actual real)
- **Backend ya es correcto**: `billing.py` `subscribe` **solo** crea el preapproval y devuelve `init_point`; el cambio real de plan ocurre vía `webhook` → `subscription_service.sync_from_preapproval_id`. → **No** hay endpoint que cambie el plan sin pago.
- **El bug está en el frontend**: `Config.jsx` `PlanSection` (~327-472) tiene botones "Cambiar a Básico/Profesional" que reflejan el cambio en la UI (optimista/local) sin esperar el pago. Auditar: que **ningún** estado local declare el plan cambiado; el único origen de verdad es `GET /billing/status`/`/auth/me`.
- `useSubscribe` → `POST /billing/subscribe` → `init_point`.

## 3. Plan secuencial
- [ ] **Audit frontend**: localizar dónde la UI marca el plan como cambiado sin confirmación. Eliminar cualquier cambio de estado local del plan.
- [ ] **Checkout en pestaña nueva**: al elegir un plan self-serve (Básico/Pro) → `POST /billing/subscribe` → abrir `init_point` con `window.open(url, '_blank', 'noopener')`. Mostrar estado "Esperando confirmación del pago…".
- [ ] **Confirmación por polling**: tras volver, **poll** `GET /billing/status` (o invalidar al focus de la ventana) hasta ver `active`/tier nuevo; recién ahí actualizar la UI y toast de éxito. Si no confirma, el plan queda como estaba.
- [ ] **Backend hardening**: confirmar que no exista ninguna ruta que permita setear `subscription.plan/status` sin pasar por el webhook firmado. Si la hubiera, removerla/gatearla. Tests que prueben que un PATCH directo no cambia el plan.
- [ ] **Modificar método de pago**: implementar el botón "Gestionar pago"/"Modificar método de pago" (hoy no hace nada) → llevar al portal de gestión de MercadoPago (o regenerar preapproval) en pestaña nueva.

## 4. Criterios de aceptación
- No se puede cambiar de plan sin completar el pago; el cambio se refleja **solo** tras confirmación de MercadoPago.
- El checkout abre en pestaña nueva; la UI muestra estado de espera y se actualiza al confirmar.
- "Modificar método de pago" funciona.
- `security-reviewer` confirma que no hay camino client-side ni endpoint que flipee el plan sin pago.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **security-reviewer** (crítico — fuente de verdad server-side, sin bypass), **react-reviewer**.
- **Workflow (obligatorio):** tras implementar correr **`/ponytail full`**; verificación visual con **Chrome MCP/Playwright en Docker local** (light+dark), simulando el flujo de cambio de plan.

## 6. Verificación
- `pytest` (ningún PATCH cambia plan sin webhook); `ruff`/`black`; `npm run build`.
- Chrome MCP/Playwright en Docker: intentar cambiar de plan → abre MP en pestaña nueva → la UI NO cambia hasta confirmar.
- `security-reviewer` sobre billing (frontend + backend).

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado (lista de bugs manual). CRÍTICO: el cambio de plan sin pago está en el frontend; backend ya cambia solo por webhook. /ponytail full + Chrome MCP/Playwright Docker obligatorios.
