---
id: KA0-scaffolding-router-v4
title: Fase 0 — Scaffolding del router v4 (plug-and-play)
status: pending
area: routers/v4
related_areas: [api/webhook, api/admin]
priority: P0
depends_on: []
created: 2026-06-23
source_items: [plan-v4-§3.1, plan-v4-§6-fase0]
---

# Fase 0 — Scaffolding del router v4

## Problema
No existe `app/routers/v4/`. Se necesita el esqueleto que clona el **contrato dict** de v3 para que
el v4 sea seleccionable por tenant (`active_router="v4"`) sin redeploy, igual que conviven v1/v2/v3 hoy.
En esta fase el engine es un stub que delega o devuelve un dict válido; lo importante es que el cableado
(adapter, schema, prompts, selección, fail-open, compuertas de seguridad) quede en su lugar.

## Anclas de contexto
- `app/routers/v3/adapter.py:process_turn_v3()` — contrato a clonar (response_text, tools_used, rich_content, confidence, router_label, latency_ms; nunca lanza, fail-open).
- `app/routers/v3/{engine,schema,prompts,guard}.py` — estructura a espejar en v4.
- `app/api/routes/webhook.py:108 _resolve_active_router()` — dónde se elige el router activo.
- `app/api/routes/admin.py:2639+` — settings per-tenant `active_router` ('' | 'v1' | 'v2' | 'v3'); agregar 'v4'.
- Compuertas de seguridad regex (emergencia, humano, fuera de alcance, `/reset`) — copiar verbatim de v3 (`guard.py`).

## Criterios de aceptación
- [ ] Existe `app/routers/v4/` con `adapter.py` exponiendo `process_turn_v4(...)` con la **misma firma y dict garantizado** que v3.
- [ ] `active_router="v4"` rutea al adapter v4 por tenant; rollback a v3 inmediato (sin redeploy).
- [ ] El adapter nunca lanza excepción (fail-open): ante error devuelve dict válido degradado.
- [ ] Compuertas de seguridad regex activas en v4 (sin LLM), idénticas a v3.
- [ ] Tests de contrato (estilo Phase 2 de v3) verdes sobre el subset garantizado.
- [ ] No rompe: v1/v2/v3 siguen seleccionables y funcionando.

## Dirección sugerida (no vinculante)
Clonar la carpeta v3 como punto de partida y vaciar el cerebro (engine), dejando el cableado.
`ponytail:` el engine de Fase 0 puede simplemente delegar a v3 o devolver un dict mínimo — la
inteligencia llega en KA1+. No construir abstracciones de "motor genérico"; v4 es un router más.

## Fuera de alcance / no tocar
No tocar webhook salvo el branch de selección. No tocar el registry de tools. No implementar
sub-goals ni memoria todavía (eso es KA1/KA2). No tocar v1/v2/v3.

## Skills / MCP / workflow recomendado
`fastapi-patterns`, `python-reviewer`. Diff mínimo; un commit por criterio. Cierra corriendo el
contrato de KA-EVAL contra v4 (debe empatar a v3 ya que delega).

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Contrato y punto de selección verificados en código.
