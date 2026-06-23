---
id: KA4-multi-accion-tools-leads
title: Fase 4 — Ejecución multi-acción + tools capture_lead / qualify_lead
status: pending
area: routers/v4
related_areas: [tools/v2, db/sales_inquiry]
priority: P1
depends_on: [KA1-percepcion-sub-objetivos]
created: 2026-06-23
source_items: [plan-v4-§3.4, plan-v4-§4, plan-v4-§6-fase4]
---

# Fase 4 — Ejecución multi-acción + tools nuevas

## Problema
El v3 ejecuta **una acción por turno** y el FSM de scheduling limita encadenar varias. El v4 debe
correr el ciclo plan→act→observe sobre los sub-objetivos (KA1), encadenando varias tools en un solo
mensaje del cliente (ej: buscar + agendar + registrar lead). Además faltan dos tools para atención al
cliente completa: `capture_lead` y `qualify_lead`.

## Anclas de contexto
- `app/tools/v2/registry.py` — registry tenant-scoped existente; las 2 tools nuevas se registran acá.
- Tools existentes (9): `search_properties`, `get_property_details`, `get_property_images`, `get_faq_answer`, `schedule_visit`, `get_my_appointments`, `cancel_appointment`, `reschedule_appointment`, `request_human_assistance`.
- `app/agents/agentic_loop.py` — patrón plan→act→observe a reusar para encadenar tools.
- Modelos para leads: `sales_inquiry.py` y `user_episode.py` (ya existen; `capture_lead`/`qualify_lead` se apoyan en ellos).
- `tenant-id-insert-rls-trap.md` (memoria) — `capture_lead` DEBE setear `tenant_id` explícito al insertar (RLS WITH CHECK rechaza NULL).
- `app/tools/v2/_common.py` — helpers/firma común de las tools.

## Criterios de aceptación
- [ ] `capture_lead` registra un lead en DB (modelo existente) con `tenant_id` explícito.
- [ ] `qualify_lead` califica (presupuesto, zona, urgencia, tipo) y marca un score.
- [ ] Un solo mensaje multi-intención ejecuta ≥2 tools encadenadas en el mismo turno (caso real verde en KA-EVAL).
- [ ] Métrica de ejecución de acciones de KA-EVAL sube respecto de v3.
- [ ] Tools tenant-scoped: no cruzan datos entre inmobiliarias.
- [ ] No rompe: las 9 tools existentes y el FSM de scheduling siguen funcionando.

## Dirección sugerida (no vinculante)
Reusar `agentic_loop.py` para el encadenado en vez de escribir un orquestador nuevo. Las 2 tools
nuevas son CRUD finos sobre modelos existentes — `ponytail:` bajo costo, no crear tablas si
`sales_inquiry`/`user_episode` alcanzan. Acotar iteraciones del loop por disciplina de costo
(mediana ≤3–4 llamadas LLM/turno).

## Fuera de alcance / no tocar
No implementar el bucle de control de decisión completo (responder/abstener/handoff → KA5). No tocar
el evaluador de evidencia (KA3). No reescribir el FSM de scheduling — reusarlo como tool.

## Skills / MCP / workflow recomendado
`tdd-guide` (escribir test de cada tool primero), `database-reviewer` (RLS en `capture_lead`),
`python-reviewer`, `cost-aware-llm-pipeline` (acotar iteraciones).

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Registry y modelos de leads confirmados en el árbol.
