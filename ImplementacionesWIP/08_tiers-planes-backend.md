---
id: 08
title: "Tiers de planes en backend — catálogo, gating por tier y montos MP"
status: completed
priority: high
area: backend
files:
  - app/core/config.py                      # MP_PLAN_PRICE_ARS / MP_PLAN_NAME (único hoy)
  - app/services/subscription_service.py    # grants_access, create_preapproval
  - app/api/deps.py                         # require_active_subscription (214) + nuevo require_plan
  - app/api/routes/billing.py               # subscribe (init_point), billing_status
  - app/api/routes/auth.py                  # /auth/me (ya expone subscription: status/plan/trial_ends_at)
  - app/api/routes/reports.py exports.py documents.py  # rutas hoy gated por suscripción → reclasificar por tier
referencia_producto:
  - recommended_pricing_plans_v3.md         # catálogo real (precios/límites/features)
  - TODO_PLANES_PRO_ENTERPRISE.md           # qué feature pertenece a qué tier
depends_on: []
note: "Base de 09 (la UI muestra tiers/límites desde acá). Enterprise NO es self-serve (CTA ventas)."
skills: ["fastapi-patterns", "python-patterns", "python-testing"]
agents: ["Plan", "security-reviewer"]
---

# Plan 08 — Tiers de planes (backend)

## 1. Objetivo
Pasar del **plan único** actual a **tres tiers** (Básico / Profesional / Enterprise) con catálogo central, **gating por tier** de las features premium, **monto MP por plan**, y exponer el tier + límites en `/auth/me` y `/billing/status` para que la UI (plan 09) los consuma. **Enterprise = sin checkout self-serve** ("Hablar con ventas").

## 2. Contexto necesario (estado actual real)

**Hoy es mono-plan:**
- `app/core/config.py`: `MP_PLAN_PRICE_ARS` y `MP_PLAN_NAME` (un solo precio/nombre). No hay enum/catálogo de tiers.
- `subscription_service.subscription_grants_access(sub)` (líneas 64-): da acceso si `active` o `trial` no vencido. **No mira el nombre del plan.**
- `subscription_service.create_preapproval(tenant_id, payer_email)`: el monto sale SIEMPRE del server (`settings`), persiste `sub.plan = settings.MP_PLAN_NAME`. → para tiers, el monto debe salir del **plan elegido**.
- `deps.require_active_subscription` (214): consulta `Subscription` por `billing_tenant` y lanza **402** si no hay acceso. Es binario (acceso/no), sin noción de tier.
- Rutas gated hoy por `require_active_subscription`: **reports, exports, documents** (3). Según el catálogo, esas son features de Pro/Enterprise, no de Básico → hay que **reclasificar por tier**.

**Catálogo real (de `recommended_pricing_plans_v3.md`) — fuente de verdad:**
| | Básico | Profesional ⭐ | Enterprise |
|---|---|---|---|
| Precio ARS/mes | 39.900 | 84.900 | desde 169.900 |
| Usuarios | 1 | 5 | ilimitados |
| Conversaciones/mes | 250 | 600 | 1.500 |
| Propiedades | 50 | ilimitadas | ilimitadas |
| Cobranzas, sitio web, reporte semanal, leads fríos | — | ✅ | ✅ |
| Multi-sucursal, documentos, reportes ejecutivos, exports, API | — | — | ✅ |

Trial: 30 días sin tarjeta. Anual −20%. Pack 100 conv extra: $12.000. Enterprise: CTA ventas (no self-serve). El mapeo feature→tier ya está en `TODO_PLANES_PRO_ENTERPRISE.md`.

## 3. Plan secuencial

> Arrancar con subagente **Plan**: fijar el **catálogo como dato** (no esparcir `if plan==...` por el código) y el contrato de límites antes de codear.

- [ ] **Catálogo central** (`app/services/plans.py` o `app/core/plans.py`): estructura por tier con `name`, `price_ars`, `price_ars_annual`, `limits` (users, conversations, properties), `features` (set de flags: `cobranzas`, `website`, `weekly_report`, `cold_leads`, `multi_branch`, `documents`, `exec_reports`, `exports`, `api`), y `self_serve: bool` (Enterprise=False). Tier order: `basico < profesional < enterprise`.
- [ ] **Gating por tier**: `deps.require_plan(*, feature=None, min_tier=None)` que: (1) exige suscripción con acceso (reusa `grants_access`), (2) verifica que el tier del `Subscription.plan` incluya la feature / alcance el `min_tier`; si no → **402** con `detail` estructurado (`{reason:'tier', required:'profesional', feature:'exports'}`) para que la UI muestre el upgrade correcto.
- [ ] **Reclasificar rutas**: cambiar `require_active_subscription` → `require_plan(feature=...)` en `reports.py` (exec_reports → enterprise), `exports.py` (exports → enterprise), `documents.py` (documents → enterprise). Revisar cobranzas/website/etc. y gatearlos a `profesional`. **Documentar** el mapeo en el catálogo, no inline.
- [ ] **Monto MP por plan**: `create_preapproval(tenant_id, payer_email, plan)` toma el precio del catálogo (no de `MP_PLAN_PRICE_ARS` global). `billing.subscribe` recibe `plan` validado contra el catálogo y **rechaza Enterprise** (no self-serve → 409/redirect a ventas). Mantener la regla "el monto sale del server".
- [ ] **Exponer en API**: `/auth/me` (ya devuelve `subscription`) + `/billing/status` agregan `tier`, `limits`, `features`, `self_serve` y el catálogo (`GET /billing/plans`) para pintar la comparativa en la UI.
- [ ] **Límites (al menos superficiar)**: exponer uso vs límite (conversaciones/usuarios/propiedades). Enforcement duro de cupos puede ser fase 2 si es caro; mínimo exponer los números. Marcar lo diferido como fase 2 (no inventar).
- [ ] **Migración de datos**: filas `subscriptions.plan` existentes → mapear al nuevo `tier` (default `profesional` para los actuales con acceso, o lo que decida el founder). Script/backfill + nota.
- [ ] **Tests** pytest: gating por feature/tier (Básico no entra a exports → 402 con reason tier; Pro sí), monto correcto por plan, Enterprise no self-serve, `grants_access` intacto para trial/active.

## 4. Criterios de aceptación
- El catálogo es la única fuente de precios/límites/features (sin literales dispersos).
- Una cuenta Básico recibe 402 `reason:tier` al pegar a una ruta Pro/Enterprise; una Pro entra a las suyas y es rechazada en las Enterprise.
- `subscribe` cobra el monto del plan elegido; Enterprise no genera preapproval self-serve.
- `/auth/me` y `/billing/status` exponen `tier/limits/features/self_serve`; `GET /billing/plans` lista el catálogo.
- `security-reviewer` aprueba (server-side pricing, fail-closed, sin escalar tier desde el cliente).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns` (deps/schemas), `python-patterns` (catálogo como dato inmutable), `python-testing`.
- **Agentes:** **Plan** (modelar catálogo + contrato de gating ANTES de codear), **security-reviewer** (precio server-side, no tier-escalation, 402 estructurado sin leak).
- **MCP:** ninguno.
- **Workflow:** catálogo → gating dep → reclasificar rutas → MP por plan → exponer API → tests. No tocar UI (eso es el plan 09).

## 6. Verificación
- `pytest` (gating, montos, no-self-serve, backfill).
- `ruff`/`black`. Arrancar Docker para correr la suite.
- Smoke: `GET /billing/plans` devuelve 3 tiers con precios del doc; `subscribe` con plan inválido → 422; Enterprise → 409.
- `security-reviewer` sobre `plans.py`, `require_plan`, `billing.subscribe`.

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Decisiones a confirmar con el founder en preflight: tier por defecto para suscripciones existentes en el backfill, y si el enforcement de cupos de conversaciones entra en v1 o fase 2.
- 2026-06-17 — Implementado y pusheado (SHA 1a567f4). Decisiones tomadas: backfill default = 'profesional'; enforcement de cupos = fase 2 (expuesto en limits pero sin hard-block). Gates: ruff ✅, 25/25 tests ✅, security-reviewer APPROVED. Archivos nuevos: plans.py (catálogo), backfill_subscription_tiers.py, test_plans_gating.py. Rutas reclasificadas: reports/exports/documents → require_plan(feature=...). GET /billing/plans público, billing/status y /auth/me exponen tier/limits/features/self_serve.
