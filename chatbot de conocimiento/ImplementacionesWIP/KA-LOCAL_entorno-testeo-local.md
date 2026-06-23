---
id: KA-LOCAL-entorno-testeo-local
title: Entorno de testeo local para el knowledge agent v4
status: completed
area: infra/testing
related_areas: [routers/v4, tests/eval]
priority: P0
depends_on: []
created: 2026-06-23
source_items: [plan-v4-§5, plan-v4-§6-fase0]
---

# Entorno de testeo local

## Problema
El v4 necesita poder ejecutarse y evaluarse **sin tocar producción**. Hoy el runtime
depende de PostgreSQL en Render (que según memoria del proyecto es la **misma DB que prod** —
`local-db-is-prod`), Redis y `OPENAI_API_KEY`. Correr el eval o probar conversaciones contra
esa DB escribe en prod. Hace falta un entorno local reproducible: DB + Redis efímeros, datos
semilla deterministas, y un modo de ejecución del agente que no dependa del webhook real de WhatsApp.

## Anclas de contexto
- `tests/conftest.py` — fixtures de test existentes; ver cómo monta DB/sesión.
- `tests/seed_properties.py`, `tests/obera_properties.json` — semilla de propiedades reusable.
- `tests/eval/runner.py` — ya rutea por el adapter; necesita runtime vivo (DB+Redis+OPENAI).
- `app/api/routes/simulate_v2.py:104` — endpoint `/simulate/multi` (entrada sin WhatsApp, ya existe).
- `docker-test-baseline.md` (memoria) — cómo se corren tests en Docker hoy; trampa de migración (tabla `notifications` en DB limpia).
- `.env` / `DATABASE_URL`, `REDIS_URL`, `OPENAI_MODEL` — variables que el agente lee.

## Criterios de aceptación
- [ ] Existe una forma documentada y de un comando para levantar Postgres+Redis **locales y efímeros** (no Render) para correr el agente.
- [ ] Hay un script/fixture de semilla determinista (propiedades, FAQ, 1 tenant de prueba) reutilizable por el eval y por pruebas manuales.
- [ ] El knowledge agent puede ejecutarse turno-a-turno localmente sin el webhook de WhatsApp (vía `/simulate/multi` o un runner directo del adapter).
- [ ] Queda escrito en `chatbot de conocimiento/` cómo arrancar el entorno y cómo apuntar el eval a la DB local (no a prod).
- [ ] No rompe: el flujo de tests en Docker existente sigue funcionando.

## Dirección sugerida (no vinculante)
Reusar lo que ya existe: Docker para Postgres+Redis (ver `docker-test-baseline.md`),
`tests/seed_properties.py` para semilla, y `/simulate/multi` como puerta de entrada sin WhatsApp.
Probablemente alcance con un `docker-compose` de test + un `.env.local` + un README corto, no infra nueva.
`ponytail:` si Docker ya levanta la DB para los tests, este plan es sobre todo documentar y
parametrizar `DATABASE_URL`, no construir un harness nuevo.

## Fuera de alcance / no tocar
No tocar `DATABASE_URL` de prod ni la config de Render. No migrar datos de prod. No crear infra
de CI nueva — solo entorno local.

## Skills / MCP / workflow recomendado
`docker-patterns`, `python-testing`. Diff mínimo; preferir reusar fixtures antes que escribir nuevas.

## Bitácora (append-only)
- 2026-06-23 — Plan creado. Verificado que `/simulate/multi` y `tests/eval/runner.py` ya existen.
- 2026-06-23 — Implementado. Creados: `tests/eval/seed_local.py` (crea tenant test-local + propiedades + 5 FAQ, guard anti-prod), `chatbot de conocimiento/ENTORNO_LOCAL.md` (docs: levantar db+redis, migraciones, semilla, correr eval, simulate manual, variables de entorno). docker-compose.eval.yml ya existía. Gates: schema imports OK, load_cases=27 casos, no se rompió infra existente.
