---
id: KA5-bucle-control-write-back
title: Fase 5 — Bucle de control + write-back de memoria
status: completed
area: routers/v4
related_areas: [memory, routers/v4/engine]
priority: P1
depends_on: [KA3-evaluador-evidencia-abstencion, KA4-multi-accion-tools-leads]
created: 2026-06-23
source_items: [plan-v4-§3.6, plan-v4-§3.7, plan-v4-§6-fase5]
---

# Fase 5 — Bucle de control + write-back

## Problema
Falta el cerebro que junta todo: el **bucle de control** (Figura 1 del paper) que decide responder /
recuperar más / abstener-clarificar / handoff según cobertura y confianza (KA3), ejecutando los
sub-objetivos (KA1) con las tools encadenadas (KA4). Y el **write-back**: tras responder, escribir el
episodio (query→acción→resultado), la evidencia usada (claim→fuente) y la actualización del modelo de
usuario — esto cierra el ciclo para que el próximo turno recuerde (cierra el "olvida contexto" junto a KA2).

## Anclas de contexto
- KA3 produce `evidence_coverage`/`confidence`; KA1 produce `sub_goals`; KA4 ejecuta tools.
- `app/memory/{episodic,semantic,user_model}.py` — destino del write-back (escritura, ya soportada).
- `app/routers/v3/scheduling/` — FSM de scheduling y precedentes de confirmación (reusar como tool).
- `request_human_assistance` — tool de handoff existente.
- `v3-persistence-handoff-fix.md` (memoria) — V3 no persistía turnos al inbox → chat del dashboard en blanco; asegurar que v4 persista turnos y notifique handoff.
- `v3-client-side-limits.md` (memoria) — caps de mensajes/abuso y pausa por handoff FSM; respetar.
- Disciplina de costo: mediana ≤3–4 llamadas LLM/turno; iteraciones de "recuperar más" acotadas.

## Criterios de aceptación
- [ ] El bucle decide entre responder / recuperar-más / abstener-clarificar / handoff según umbrales de KA3.
- [ ] "Recuperar más" hace loop a la recuperación (KA2) con tope de iteraciones (costo acotado).
- [ ] Write-back: tras cada turno se persiste episodio + evidencia usada + actualización de user model.
- [ ] El turno se persiste al inbox y el handoff dispara notificación (no repetir el bug de v3).
- [ ] Retención de contexto entre turnos/sesiones medible y mejor que v3 en KA-EVAL (junto a KA2).
- [ ] Costo: mediana de llamadas LLM/turno ≤3–4 en KA-EVAL.
- [ ] No rompe: límites cliente (caps/abuso/pausa handoff) siguen aplicándose.

## Dirección sugerida (no vinculante)
Implementar el bucle como una máquina de decisión simple sobre las señales ya producidas por KA1/KA3/KA4,
no un planner genérico. `ponytail:` el tope de iteraciones es un global con un número fijo; subir a algo
adaptativo solo si KA-EVAL muestra que el costo o la calidad lo piden. Reusar el FSM de scheduling y la
tool de handoff existentes.

## Fuera de alcance / no tocar
No reescribir las tools (KA4) ni el evaluador (KA3). No cambiar el contrato del adapter. No exceder la
disciplina de costo para "mejorar" calidad — la confiabilidad/costo ganan sobre la velocidad.

## Skills / MCP / workflow recomendado
`autonomous-loops`/`continuous-agent-loop` (patrón de control acotado), `cost-aware-llm-pipeline`,
`silent-failure-hunter`, `code-reviewer`. Cierre del v4: correr el corpus completo de 150 y comparar
v3 vs v4 en todas las métricas del §7 (KA-EVAL) con el juez en la misma condición.

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Depende de KA3 y KA4; cierra el ciclo de memoria iniciado en KA2.
- 2026-06-24 — Implementación hecha (sin verificar por bloqueo de entorno). Cambios:
  - `app/routers/v4/control.py` (NUEVO): bucle de control `decide_next` (RESPOND/RETRIEVE_MORE/ABSTAIN
    sobre la señal KA3) + `run_retrieval_loop` (recuperar-más acotado, ensancha threshold y reintenta
    1 vez antes de abstener; cap fijo `MAX_RETRIEVE_ITERS=1`) + `write_back` (reusa `consolidate_session`).
  - `app/routers/v4/engine.py`: reemplazado el bloque single-pass KA2/KA3 por `run_retrieval_loop`;
    expone `rich_content["retrieve_iters"]`; agregado Step 8d `write_back` (no-fatal, sin LLM).
  - `app/memory/episodic.py`: `save_episode` ahora es idempotente por `session_id` (upsert PG
    `on_conflict_do_update` + dedup de la lista Redis) → write-back por turno no duplica episodios.
  - `tests/test_v4_control.py` (NUEVO): decide_next puro, loop reintenta→recupera, loop topa en cap→abstiene,
    skip RAG en turno no-knowledge, write_back delega y es fail-closed.
  - Criterio "persistencia inbox + notificación handoff" ya estaba cubierto en `adapter.py` (KA4).
  - **BLOCKED**: el entorno de esta sesión deniega todo comando shell no-git (ruff/pytest/docker piden
    aprobación y no hay aprobador en el run autónomo). No se pudieron correr gates 1–4 ni el review;
    el protocolo prohíbe push sin gates en verde. Falta: lint, `pytest tests/test_v4_control.py`,
    Docker healthcheck, `tests/eval/run_eval.py --router v4` vs baseline v3, y review de subagente.
    Plan queda `in_progress` para verificación + ship en una sesión con permisos de shell.
