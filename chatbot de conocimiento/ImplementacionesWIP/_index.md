# Índice — Knowledge Agent v4 (ImplementacionesWIP)

Planes derivados de `../PLAN_Knowledge_Agent_v4.md`. Todo el trabajo de planificación,
corpus de evaluación y scripts de testeo local del knowledge agent vive en `chatbot de conocimiento/`
(el código de runtime necesariamente vive en `app/routers/v4/` — ahí no hay forma de contenerlo).

Orden de ejecución: **KA-LOCAL → KA-EVAL → KA0 → KA1 → (KA2 ∥ KA4) → KA3 → KA5**.
KA-EVAL se construye temprano para medir cada fase contra v3 con datos reales.

| id | área | prioridad | estado | depends_on |
|----|------|-----------|--------|------------|
| KA-LOCAL | infra/testing | P0 | completed | — |
| KA-EVAL | tests/eval | P0 | completed | KA-LOCAL |
| KA0 | routers/v4 | P0 | completed | — |
| KA1 | routers/v4 (percepción) | P0 | completed | KA0 |
| KA2 | routers/v4 + memory | P1 | completed | KA1 |
| KA3 | routers/v4 (evidencia) | P1 | pending | KA2 |
| KA4 | routers/v4 + tools/v2 | P1 | pending | KA1 |
| KA5 | routers/v4 (control loop) | P1 | pending | KA3, KA4 |

## Regla de verificación transversal
Cada fase KA0–KA5 cierra corriendo `tests/eval/run_eval.py --router v4` (ver KA-EVAL) y
comparando contra el baseline v3 sobre `angelo-hard-test-conversations-150.md`. Una fase no se
da por terminada si rompe una métrica que ya estaba en verde.
