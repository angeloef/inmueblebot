---
id: enforcement-limites-plan-backend
status: completed
priority: P0
area: Backend (plans/deps/admin)
files:
  - app/services/plans.py
  - app/api/deps.py
  - app/api/routes/admin.py
endpoints:
  - POST /properties (alta de propiedad)
  - POST team / invite (alta/invitación de miembro)
depends_on: []
related_areas: [09_flujo-saas-frontend, 22_gating-candado-enterprise-audit]
skills: [fastapi-patterns, python-testing]
agents: [security-reviewer, fastapi-reviewer]
---

# 41 — Enforcement de límites cuantitativos por plan

## 1. Objetivo
Aplicar realmente los límites numéricos del plan. Hoy `plans.py` los **define** pero
**nadie los chequea**: un tenant Básico puede cargar >50 propiedades e invitar miembros
sin tope. Bloqueo duro con 402 al exceder; el front ya sabe abrir el UpgradeModal con 402.

## 2. Contexto necesario
- `app/services/plans.py:39-70` — `PlanLimits(users, conversations_per_month, properties)`.
  Básico: `users=1, properties=50`. Pro: `users=5, properties=None(ilimitado)`.
  Enterprise: `users=None, properties=None`. `None = ilimitado`.
- `app/api/deps.py:238-287` — `require_plan(feature, min_tier)` valida suscripción + feature
  + tier, pero **no cuenta recursos**. Devuelve 402 con `detail.reason` (`subscription`|`tier`).
  Reusar este patrón de error para los límites.
- `app/api/routes/admin.py` — endpoints de alta de propiedad y de alta/invitación de equipo
  (buscar el `@router.post` de properties y el de team/members; no están gateados por cantidad).
- El front interpreta 402 vía interceptor → `subscription:required` → `UpgradeModal`
  (`dashboard/src/Shell.jsx:278`, `featureGates.js:dispatchUpgradeEvent`). Para que el modal
  tenga copy útil, el 402 debe traer `detail.reason="limit"`, `detail.resource`, `detail.limit`,
  `detail.current_tier`.

## 3. Plan secuencial
- [ ] Agregar helper en deps/plans: `enforce_resource_limit(resource: "properties"|"users", current_count, plan)` que lance 402 `{reason:"limit", resource, limit, current}` si `limit is not None and current >= limit`.
- [ ] En el POST de alta de propiedad: contar propiedades del tenant (RLS-scoped) antes de insertar y llamar al helper.
- [ ] En el POST de alta/invitación de miembro: contar miembros activos del tenant y llamar al helper.
- [ ] Revisar `conversations_per_month` — ¿hay alta de conversaciones gateable? Si no aplica acá, dejar fuera de alcance y anotarlo.
- [ ] Cuentas ya excedidas: **no** borrar ni migrar; el chequeo `>=` simplemente bloquea altas nuevas. Verificar que un tenant con 60/50 no rompe lectura, solo el alta.
- [ ] (Front, opcional menor) extender el copy del UpgradeModal para `reason="limit"` ("Alcanzaste el límite de N propiedades de tu plan").

## 4. Criterios de aceptación
- Tenant Básico con 50 propiedades → POST nº51 responde **402** `reason:"limit"`, no inserta.
- Tenant Básico con 1 miembro → invitar 2º responde **402** `reason:"limit"`.
- Tenant Pro/Enterprise (limit `None`) → sin tope, altas siguen funcionando.
- Conteos son **por tenant** (RLS) y no cuentan otros tenants.
- Tests: unit del helper (límite None, bajo, en el borde, excedido) + integración de los 2 endpoints.

## 5. Skills / MCP / Workflow AI
`/ponytail full`. TDD con `python-testing`. Review final con `security-reviewer` (bypass de límite = revenue leak) y `fastapi-reviewer`.

## 6. Verificación
- `pytest` de los nuevos tests en Docker (ver `docker-test-baseline`).
- Manual: login como inmobiliaria Obrá (Básico) y probar el alta nº51 / 2º miembro.

## 7. Bitácora (append-only)
- 2026-06-20: plan creado. Hallazgo: `plans.py` define límites pero `deps.py:require_plan` nunca cuenta recursos → límites inertes. Decisión del dueño: bloqueo duro + 402/UpgradeModal; no tocar cuentas ya excedidas.
- 2026-06-20: implementado. `deps.py`: helper puro `enforce_resource_limit(resource, current, plan)` (402 `reason:limit` con resource/limit/current/current_tier) + `get_account_plan`/`get_account_plan_sync`. `admin.create_property` (sync) cuenta `Property` RLS-scoped antes de insertar; mantiene `require_active_subscription`. `team.invite_member` (async) usa `team_service.count_users` (cuentas del org + invitaciones pendientes) y enforce. Tests: 5 unit del helper (None/below/borde/excedido/users) en `test_plans_gating.py` (33 pass en Docker). `conversations_per_month` sin endpoint de alta self-serve (WhatsApp inbound) → fuera de alcance. No hay bulk-import programático: `property_imports` es pedido manual procesado por devs, no inserta Property en self-serve. `/ponytail full`: diff backend-only, sin abstracciones de más; copy de UpgradeModal para `reason:limit` deferido (modal genérico ya abre + CTA funcional; el shape 402 viene anidado en `response.data.detail`, tocarlo arriesgaba el path de tier). Gates: lint (solo baseline preexistente), tests, imports OK.
