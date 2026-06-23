---
id: KA-EVAL-framework-evaluacion
title: Framework de evaluación del knowledge agent (métricas con datos reales)
status: pending
area: tests/eval
related_areas: [routers/v4]
priority: P0
depends_on: [KA-LOCAL-entorno-testeo-local]
created: 2026-06-23
source_items: [plan-v4-§7]
---

# Framework de evaluación

## Problema
Para saber si el v4 supera al v3 hacen falta **métricas basadas en datos reales**, no impresiones.
Ya existe un harness (`tests/eval/`) que rutea por el adapter, soporta `--router`, hold-out/dev split,
pass@k, juez LLM y snapshot de baseline. Lo que falta: (a) soportar `--router v4`, (b) las métricas
específicas del knowledge agent del §7 del plan (multi-intención, retención de contexto/anáfora,
grounding/anti-alucinación, ejecución de acciones, cobertura de evidencia y confianza), y (c) anclar
los casos al corpus real `angelo-hard-test-conversations-150.md`. El framework debe permitir medir
**cada fase a medida que se implementa** y comparar A/B v3 vs v4.

## Anclas de contexto
- `tests/eval/run_eval.py` — CLI; ya tiene `--router`, `--split`, `--k`, `--no-model`, `--snapshot`.
- `tests/eval/runner.py` — `run_case()`; rutea por el adapter (acá se agrega rama v4).
- `tests/eval/metrics.py` — `CaseResult`, `aggregate()`; acá se suman las métricas nuevas.
- `tests/eval/graders.py`, `tests/eval/schema.py`, `tests/eval/cases/` — definición y carga de casos.
- `tests/eval/baseline-v2.json` — patrón de snapshot; se necesita un `baseline-v3.json` análogo.
- `tests/eval/test_knowledge_grounding.py` — ya existe; punto de partida para el grader de grounding.
- `angelo-hard-test-conversations-150.md` (raíz) — corpus de conversaciones reales para los casos.
- `v3-eval-baseline-mismatch.md` (memoria) — CRÍTICO: el 0.52-vs-0.75 fue juez-on vs juez-off, NO v3 atrás de v2. Mantener juez consistente al comparar.

## Criterios de aceptación
- [ ] `run_eval.py --router v4` ejecuta el corpus contra el adapter v4 (rama agregada en `runner.py`).
- [ ] Métricas del §7 implementadas y reportadas por corrida, cada una **verificable por dato**, no por opinión:
  - [ ] Multi-intención: % de turnos con ≥2 sub-objetivos resueltos.
  - [ ] Retención de contexto: % de referencias anafóricas resueltas correctamente entre turnos/sesiones.
  - [ ] Grounding: % de afirmaciones sobre propiedades con `property_id` real; tasa de abstención correcta.
  - [ ] Ejecución de acciones: % de intenciones accionables efectivamente ejecutadas (tool llamada).
  - [ ] Cobertura de evidencia y confianza promedio por turno.
  - [ ] Costo: mediana de llamadas LLM/turno.
- [ ] Existe `baseline-v3.json` snapshot para comparar; el reporte muestra diff v3 vs v4 en la misma corrida/condición de juez.
- [ ] Los casos se derivan del corpus real `angelo-hard-test-conversations-150.md` (no inventados).
- [ ] Corre contra la **DB local** de KA-LOCAL, nunca prod.
- [ ] No rompe: las métricas y casos v2/v3 existentes siguen reportándose igual.

## Dirección sugerida (no vinculante)
Extender, no reescribir. Agregar la rama `v4` en `runner.py` análoga a v3, sumar campos a
`metrics.py`/`report.py`, y derivar casos etiquetados (`tags`) por métrica desde el corpus real.
Para grounding/abstención reusar `test_knowledge_grounding.py`. Las métricas que necesitan
"verdad" (anáfora resuelta, sub-goal resuelto) conviene marcarlas como aserciones por caso en el
schema de casos, no inferirlas con el juez, para que sean datos duros.

## Fuera de alcance / no tocar
No cambiar el contrato del adapter. No automatizar promoción (sigue siendo manual, D5). No reemplazar
el juez LLM existente. No medir fases todavía no implementadas como "fallo" — etiquetar como N/A.

## Skills / MCP / workflow recomendado
`eval-harness`, `python-testing`, `agent-eval`. Workflow: escribir primero el caso+aserción de la
métrica, luego correrla en rojo contra v3 para fijar baseline, luego habilitar v4.

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Confirmado que `tests/eval/` ya soporta `--router` y snapshot; esto es extensión.
