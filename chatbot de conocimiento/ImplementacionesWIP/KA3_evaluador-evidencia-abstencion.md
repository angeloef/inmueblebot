---
id: KA3-evaluador-evidencia-abstencion
title: Fase 3 — Evaluador de evidencia + abstención (anti-alucinación)
status: completed
area: routers/v4
related_areas: [routers/v4/engine]
priority: P1
depends_on: [KA2-recuperador-evidencia-memoria]
created: 2026-06-23
source_items: [plan-v4-§3.5, plan-v4-§6-fase3]
---

# Fase 3 — Evaluador de evidencia + abstención

## Problema
Riesgo crítico para inmobiliaria: **alucinar propiedades/precios**. El v4 debe evaluar el pool de
evidencia (KA2) antes de responder y producir `evidence_coverage` + `confidence`. Regla dura: si una
afirmación sobre una propiedad **no tiene evidencia con id real**, no se afirma. Cuando la evidencia
es insuficiente/contradictoria, el agente **se abstiene o clarifica** en vez de inventar.

## Anclas de contexto
- Pool de evidencia con procedencia producido por KA2 (entrada de esta fase).
- `app/routers/v3/engine.py` / `app/agents/evaluator.py` — patrón de evaluación existente a reusar/extender.
- `tests/eval/test_knowledge_grounding.py` — grader de grounding que KA-EVAL usa para medir esto.
- 5 dimensiones del paper: completitud, profundidad, recencia, autoridad, consistencia.
- `v3-photo-delivery-and-smalltalk.md` / `v3-scheduling-bulletproof.md` (memoria) — precedentes de "fail-closed" y confirmaciones ancladas a datos reales; mantener esa filosofía.

## Criterios de aceptación
- [ ] Antes de responder se calcula `evidence_coverage` y `confidence` sobre las 5 dimensiones.
- [ ] Toda afirmación sobre una propiedad referencia un `property_id` real del pool (grounding ~100% en KA-EVAL).
- [ ] Ante evidencia insuficiente/contradictoria el agente se abstiene o clarifica (no inventa); medible como "abstención correcta" en KA-EVAL.
- [ ] La métrica de grounding/anti-alucinación de KA-EVAL no empeora ninguna métrica previa en verde.
- [ ] No rompe: respuestas con evidencia suficiente siguen fluyendo sin fricción extra innecesaria.

## Dirección sugerida (no vinculante)
El evaluador puede ser determinista sobre el pool (chequeo de que cada claim tiene id) + un score de
confianza; no necesariamente otra llamada LLM. `ponytail:` empezar con umbrales simples sobre cobertura
y subir sofisticación solo si KA-EVAL muestra que hace falta. La decisión final (responder/abstener/
recuperar más) la toma el bucle de control de KA5; acá se produce la señal.

## Fuera de alcance / no tocar
No implementar el loop de "recuperar más" ni handoff (KA5). No tools nuevas. No relajar el grounding
para mejorar fluidez — la transparencia gana sobre la fluidez (principio §2).

## Skills / MCP / workflow recomendado
`silent-failure-hunter` (que la abstención no se trague errores), `python-reviewer`, `eval-harness`.
Escribir primero casos de abstención en KA-EVAL (pregunta sin evidencia → debe abstenerse).

## Bitácora (append-only)
- 2026-06-23 — Plan creado. `app/agents/evaluator.py` y `test_knowledge_grounding.py` existen como base.
- 2026-06-24 — Implementado. Gates: lint OK, 37 tests green (16 nuevos KA3 + 21 preexistentes KA2/grounding). SHA: 8712238. Ponytail: abstention_response()→constante; consistency=0.0 (honest baseline). Review: python-reviewer APPROVE, silent-failure-hunter encontró 3 findings (MEDIUM consistency→fixed, LOW malformed pool warning→added, LOW str() casts→added).
