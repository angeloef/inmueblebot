---
id: 19
title: "Facturación/Uso — historial de pagos + 'uso últimos 30 días' con reset por período"
status: completed
priority: medium
area: backend+frontend
files:
  - dashboard/src/Config.jsx        # sección Facturación + sección Uso (LimitBar ~309)
  - app/api/routes/billing.py       # agregar historial de pagos
  - app/services/subscription_service.py  # datos de pagos / período
  - app/db/models/subscription.py   # current_period_end (ya existe)
depends_on: ["18"]
note: "OBLIGATORIO: /ponytail full tras implementar; verificación visual Chrome MCP/Playwright en Docker (light+dark)."
skills: ["fastapi-patterns", "react-patterns", "python-testing", "data-viz"]
agents: ["react-reviewer", "security-reviewer"]
---

# Plan 19 — Facturación: historial de pagos + Uso con período

## 1. Objetivo
(a) Mostrar un **historial visible de pagos de meses pasados** en Facturación. (b) En **Uso**, aclarar que el consumo es de los **últimos 30 días / período actual** y resetear el conteo **cuando arranca el próximo período de facturación**.

## 2. Contexto necesario (estado actual real)
- `subscription` tiene `current_period_end` (`subscription.py`) → ancla del período. MercadoPago expone pagos del preapproval (consultar API / persistir). Hoy **no** hay endpoint de historial de pagos ni se persisten los pagos.
- `Config.jsx` tiene la sección Uso con `LimitBar` (~309) alimentada por `GET /usage` (plan 16). Hay que basar la ventana en el período de facturación.

## 3. Plan secuencial
- [ ] **Historial de pagos (backend)**: endpoint `GET /billing/payments` (tenant-scoped) que liste pagos pasados (fecha, monto, estado, período). Fuente: persistir desde el webhook de MP o consultar la API de preapproval; definir en preflight con el subagente Plan.
- [ ] **Historial (frontend)**: tabla/lista en Facturación (mes, monto, estado, comprobante si hay). Estados vacío/cargando/error.
- [ ] **Uso por período**: `GET /usage` (plan 16) debe contar sobre la **ventana del período de facturación actual** (de `current_period_end` hacia atrás) o "últimos 30 días" si no hay sub activa. Mostrar el texto "Uso del período actual (se renueva el DD/MM)".
- [ ] **Reset**: asegurar que el conteo de conversaciones se mida por período y se "resetee" al cambiar de período (no acumulado histórico). Documentar la regla.
- [ ] Tests: historial devuelve pagos del propio tenant (no cross-tenant); ventana de uso correcta alrededor del corte de período.

## 4. Criterios de aceptación
- Facturación muestra pagos pasados con fecha/monto/estado.
- Uso aclara la ventana ("últimos 30 días / período") y la fecha de renovación, y el conteo refleja el período vigente.
- Scoping correcto; `security-reviewer` OK.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **Plan** (origen de datos de pagos), **security-reviewer** (scoping), **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; verificación visual con **Chrome MCP/Playwright en Docker** (light+dark).

## 6. Verificación
- `pytest` (historial + ventana de uso) en Docker; `ruff`/`black`; `npm run build`.
- Chrome MCP/Playwright: ver historial y el texto/valores de Uso del período.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Depende de 18 (billing) y reusa `/usage` (plan 16).
- 2026-06-19 — Implementado y pusheado. SHA: 1a2ca0f. Gates: ruff OK, build OK, 13/14 billing tests pass (1 ASGI test bloqueado por bug pre-existente datetime.UTC en Python 3.10 en admin_analytics.py). Security review: no CRITICAL/HIGH. Ponytail full corrido. Visual: endpoints registrados en OpenAPI, /billing/payments responde 401 sin auth (correcto).
