---
id: KA1-percepcion-sub-objetivos
title: Fase 1 — Percepción + descomponedor de objetivos (multi-intención)
status: pending
area: routers/v4
related_areas: [routers/v4/schema, routers/v4/prompts]
priority: P0
depends_on: [KA0-scaffolding-router-v4]
created: 2026-06-23
source_items: [plan-v4-§3.2, plan-v4-§6-fase1]
---

# Fase 1 — Percepción + sub-objetivos

## Problema
El v3 colapsa cada mensaje a **un intent + una action** (`routers/v3/schema.py:89–114`), aplanando
matices y matando la multi-intención ("quiero ver el depto del centro y agendar para el sábado").
El v4 reemplaza ese schema por una pasada estructurada que devuelve `belief_delta` (como v3) más una
lista ordenada de `sub_goals[]` y `references` (anáfora / `selected_property_id`). Esta fase arregla
"no entiende NL" y "multi-intención": el mensaje se descompone en N sub-objetivos.

## Anclas de contexto
- `app/routers/v3/schema.py:89–114` — el schema "1 intent / 1 action" que se reemplaza.
- `app/routers/v3/engine.py` — pasada schema-guiada actual (referencia del patrón LLM estructurado).
- `app/routers/v3/prompts.py` — prompts a adaptar para emitir `sub_goals`/`references`.
- `app/routers/v3/belief.py` (`BeliefStateV5`) — `belief_delta` se conserva igual.
- Modelo: `gpt-5.4-mini` vía `OPENAI_MODEL`/`LLM_MODEL_*` (mismo que v3, disciplina de costo).
- Schema objetivo (del plan §3.2): `{ belief_delta, sub_goals[{intent,args_hint}], references{selected_property_id, anaphora}, confidence }`.
- `v3-parse-fallback-clarify-loop.md` (memoria) — trampa: parse JSON falla con texto sobrante → usar `raw_decode`. No repetir.

## Criterios de aceptación
- [ ] El engine v4 emite `sub_goals[]` ordenados (≥0) además del `belief_delta`.
- [ ] Un mensaje multi-intención produce ≥2 sub_goals (caso real del corpus verde en KA-EVAL).
- [ ] `references.anaphora` / `selected_property_id` se extraen cuando aplican.
- [ ] Parseo robusto a texto sobrante del LLM (estilo `raw_decode`, sin re-preguntar slots ya respondidos).
- [ ] Métrica de multi-intención de KA-EVAL ≫ v3 (que es ~0).
- [ ] No rompe: turnos de una sola intención siguen funcionando con confianza comparable a v3.

## Dirección sugerida (no vinculante)
Una sola llamada estructurada que extienda el schema v3, no dos pasadas. Reusar el manejo de
`belief_delta` tal cual. El bucle de control que *ejecuta* los sub_goals llega en KA5; acá solo se
producen y se persisten en el estado del turno.

## Fuera de alcance / no tocar
No implementar el recuperador de evidencia (KA2) ni la ejecución encadenada (KA5). No agregar tools.
No tocar las compuertas de seguridad. Mantener una sola llamada LLM en esta etapa (costo).

## Skills / MCP / workflow recomendado
`regex-vs-llm-structured-text`, `cost-aware-llm-pipeline`, `python-reviewer`. Escribir primero los
casos de multi-intención/anáfora en KA-EVAL, luego implementar hasta ponerlos en verde.

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Schema v3 mono-intent confirmado en schema.py.
