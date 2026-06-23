# Entorno local — Knowledge Agent v4

Cómo correr el agente y el eval **sin tocar producción**.
La DB local es efímera; los datos de prod viven en Render y no se tocan.

---

## 1. Levantar Postgres + Redis locales

```bash
# Desde la raíz del repo
docker compose -f docker-compose.yml -f docker-compose.eval.yml up -d db redis
```

Esto levanta:
- `inmueblebot-db` → Postgres 16 + pgvector en `localhost:5432`
- `inmueblebot-redis` → Redis 7 en `localhost:6379`

Esperar que ambos servicios estén healthy (unos 10 s):
```bash
docker compose ps
```

---

## 2. Aplicar migraciones

```bash
# Puntear a la DB local y correr migraciones Alembic
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot \
alembic upgrade head
```

> La DB local arranca vacía; sin este paso los modelos no existen.

---

## 3. Semilla determinista

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot \
REDIS_URL=redis://localhost:6379/0 \
python -m tests.eval.seed_local
```

Crea:
- 1 tenant de prueba (`slug=test-local`)
- 50 propiedades en Oberá (desde `tests/obera_properties.json`)
- 5 entradas de FAQ con datos reales

Si `tests/obera_properties.json` no existe, generarlo primero:
```bash
python tests/seed_properties.py
```

---

## 4. Correr el eval contra la DB local

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot \
REDIS_URL=redis://localhost:6379/0 \
OPENAI_API_KEY=<tu-key> \
python -m tests.eval.run_eval --router v3 --split dev --no-model --k 1
```

`--no-model` omite el juez LLM (útil para iterar rápido sin gastar tokens).
`--router v4` disponible una vez que KA0 esté completo.

Para tomar snapshot baseline de v3:
```bash
DATABASE_URL=... REDIS_URL=... OPENAI_API_KEY=... \
python -m tests.eval.run_eval --router v3 --split all --k 1 --snapshot
```

---

## 5. Prueba manual turno a turno (sin WhatsApp)

```bash
# Con el stack completo levantado (docker compose up -d)
curl -sS -X POST http://localhost:9000/simulate/multi \
  -H "Content-Type: application/json" \
  -d '{"message": "busco depto en alquiler en Oberá", "session_id": "local-test-01", "phone": "549-local-01"}'
```

El endpoint `POST /simulate/multi` no requiere auth y devuelve
`tools_called`, `router`, `selection`, `active_intents` — exactamente lo
que compara el eval harness.

---

## Variables de entorno clave

| Variable | Local | Producción |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot` | ← Render (no tocar) |
| `REDIS_URL` | `redis://localhost:6379/0` | ← Render (no tocar) |
| `OPENAI_API_KEY` | tu key personal | misma key (OK) |
| `OPENAI_MODEL` | `gpt-4.1-mini` (default) | igual |

Copiar `.env` a `.env.local` y reemplazar sólo `DATABASE_URL` y `REDIS_URL`
para no pisar la config de producción:

```bash
cp .env .env.local
# Editar .env.local:
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot
# REDIS_URL=redis://localhost:6379/0
```

Usar `.env.local` al correr:
```bash
export $(grep -v '^#' .env.local | xargs)
python -m tests.eval.run_eval --router v3 --split dev --no-model
```

---

## Bajar el entorno local

```bash
docker compose -f docker-compose.yml -f docker-compose.eval.yml down
```

Los datos se pierden (volumen efímero). Para preservarlos entre sesiones
omitir `down` y usar sólo `stop`.
