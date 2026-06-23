---
id: KA5-bucle-control-write-back
title: Fase 5 — Bucle de control + write-back de memoria
status: pending
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
