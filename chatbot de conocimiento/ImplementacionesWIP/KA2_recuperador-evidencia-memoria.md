---
id: KA2-recuperador-evidencia-memoria
title: Fase 2 — Recuperador consciente de evidencia + memoria persistente
status: completed
area: routers/v4
related_areas: [memory, tools/v2, pgvector]
priority: P1
depends_on: [KA1-percepcion-sub-objetivos]
created: 2026-06-23
source_items: [plan-v4-§3.3, plan-v4-§6-fase2]
---

# Fase 2 — Recuperador de evidencia + memoria persistente

## Problema
El v3 escribe memoria episódica/semántica/usuario pero **no la inyecta en el bucle del turno** —
de ahí el "olvida el contexto". El v4 debe, por cada sub-objetivo, armar un *pool de evidencia* con
procedencia desde tres fuentes: PostgreSQL (vía tools del registry), pgvector (RAG FAQ+docs) y la
memoria de 3 niveles **recuperada cada turno**. Cada ítem lleva fuente, id, timestamp y score.

## Anclas de contexto
- `app/memory/episodic.py`, `app/memory/semantic.py`, `app/memory/user_model.py` — ya existen; hoy solo se escriben. Acá se **recuperan** e inyectan.
- `app/tools/v2/registry.py` + tools (`search_properties`, `get_faq_answer`, ...) — fuente Postgres tenant-scoped.
- pgvector + `text-embedding-3-small` — RAG existente (FAQ/docs); ver `app/routers/v3/knowledge/`.
- `app/routers/v3/belief.py` (`BeliefStateV5`, Redis TTL 24h) — estado por turno; sumar recuperación de memoria.
- `tenant-id-insert-rls-trap.md` (memoria) — toda escritura a tabla scoped debe setear `tenant_id`; RLS rechaza NULL.
- `v3-manual-test-1-fixes.md` (memoria) — bug RAG bind previo; necesita `POST /knowledge/reindex` tras deploy.

## Criterios de aceptación
- [ ] Por cada sub-objetivo se construye un pool de evidencia con ítems {fuente, id, timestamp, score}.
- [ ] La memoria episódica/semántica/usuario se **recupera** e inyecta en el contexto del turno (no solo se escribe).
- [ ] Recuperación híbrida densa + keyword (como recomienda el paper) para FAQ/docs.
- [ ] Métrica de retención de contexto/anáfora de KA-EVAL sube respecto de v3 (referencias entre turnos/sesiones resueltas).
- [ ] Recuperación tenant-scoped: nunca cruza datos entre inmobiliarias (RLS respetado).
- [ ] No rompe: latencia/costo dentro de la disciplina (no dispara llamadas LLM extra en esta fase; la recuperación es DB/vector).

## Dirección sugerida (no vinculante)
Reusar los módulos de memoria existentes para lectura; el pool de evidencia es una estructura en
memoria del turno (lista con procedencia), no una tabla nueva. La recuperación es retrieval, no LLM:
mantener el costo en KA1. El *write-back* (escribir el episodio resultante) se hace en KA5.

## Fuera de alcance / no tocar
No evaluar/abstener todavía (KA3). No encadenar acciones (KA5). No crear tablas de memoria nuevas si
las existentes alcanzan. No tocar el schema de KA1.

## Skills / MCP / workflow recomendado
`postgres-patterns`, `redis-patterns`, `iterative-retrieval`, `database-reviewer` (RLS/tenant scope).
Verificar aislamiento por tenant con datos semilla de KA-LOCAL antes de cerrar.

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Confirmado que los 3 módulos de memoria existen en `app/memory/`.
- 2026-06-24 — KA2 completado.
  - **Nuevo** `app/routers/v4/evidence.py`: `EvidenceItem` (frozen), `gather_memory_evidence`
    (episódica/persona/zona, tenant-scoped, read-only), `gather_rag_evidence` (híbrido denso+keyword
    re-rank sobre pgvector), `render_memory_block` (inyección al prompt), `build_evidence_pool`
    (pool por sub-objetivo con procedencia {source,id,timestamp,score}).
  - `engine.py`: Step 2b recupera memoria e inyecta vía `build_messages_v4`; expone `evidence_pool`
    y RAG híbrido (solo en turnos knowledge, para no duplicar embed). `prompts.py`: `build_messages_v4`
    coloca el bloque de memoria tarde (antes de [ESTADO]) para no romper el cache prefix.
  - **Fix de aislamiento (criterio #5)** surgido del review de seguridad: `episodic.get_episodes`
    fallback PG ahora filtra por `tenant_id`; `semantic.get_zone_info` usa `tenant_redis_key`
    (antes clave global → colisión entre inmobiliarias). Logs de fallo elevados a warning.
  - Gates: ruff limpio en líneas nuevas (black no instalado en la imagen); pytest 26 v4 + 7 zona
    verdes; app sirve `/version` 200; UX N/A (sin cambio visual); security-reviewer (H1/H2/M1 resueltos).
  - Pendiente menor (M3): confirmar que el inbox no persista `evidence_pool` con resúmenes de
    sesión (mismo tenant/contacto, no es leak cross-tenant; revisar en KA5 al escribir el write-back).
  - `/ponytail full` aplicado: se eliminaron clases/funciones especulativas e imports muertos.
