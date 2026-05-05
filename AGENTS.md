# InmuebleBot — Agent Guide

## Entrypoints

- **FastAPI app**: `app/main.py` — uvicorn entrypoint: `app.main:app`
- **Docker compose**: `docker compose up -d` (starts db, redis, app, streamlit UI, dashboard)
- **Dashboard**: `http://localhost:3000` (Vite dev) or `http://localhost:9000/dashboard` (production build)
- **Render deploy**: `render.yaml` — uses `env: docker` → `Dockerfile` (multi-stage: python:3.12-slim)

## Developer Commands

```bash
uvicorn app.main:app --reload              # Dev server (port 8000)
cd dashboard && npm install && npm run dev  # Dashboard Vite dev (port 5173)
cd dashboard && npm run build              # Build dashboard SPA → dashboard/dist/
pytest tests/ -v                           # All tests
ruff check app/ tests/                     # Lint
mypy app/                                  # Typecheck
pip install -r requirements.txt            # Install deps
```

**Order**: `ruff check .` → `mypy app/` → `pytest tests/ -v`

## Architecture

- **`app/agents/`** — LLM routers (Gemini, OpenRouter, MiniMax), prompts, tools, real_estate_agent
- **`app/api/routes/`** — Webhook, admin CRUD (sync psycopg2), internal
- **`app/core/`** — Config (pydantic-settings), memory, state machine, intent
- **`app/db/`** — SQLAlchemy async, models (User, Conversation, Message, Property, Appointment), alembic
- **`app/services/`** — Property, appointment, calendar, lead, handoff, notification
- **`app/integrations/`** — WhatsApp (Meta + Twilio), Calendar (Google), Storage
- **`app/utils/`** — Sanitizer, rate_limiter (in-memory), date_parser, lang_detector, logger
- **`frontend/`** — Streamlit chat UI (port 8502)
- **`dashboard/`** — React SPA admin panel (Vite, @tanstack/react-query, axios)

## Critical Quirks

1. **DATABASE_URL must use asyncpg driver**: `resolved_database_url` in `config.py:184` auto-adds `+asyncpg` to `postgresql://` URLs (Render provides plain `postgresql://`)
2. **Python 3.14 breaks SQLAlchemy 2.0**: Dockerfile pins `python:3.12-slim`. Model annotations MUST use `Optional[X]` not `X | None` — triggers `descriptor '__getitem__' requires a 'typing.Union' object` on Python 3.14
3. **Admin routes use sync psycopg2**: Lazy-initialized sync session in `admin.py` strips `+asyncpg` from URL. psycopg2-binary required in requirements.txt
4. **Webhook double-prefix bug**: Router mounted at `/webhook`. Routes must NOT start with `/webhook/...` or actual path becomes `/webhook/webhook/whatsapp`
5. **JSON logging**: `loguru serialize=True` in `main.py` — structured JSON for Render log streams
6. **WhatsApp phone formatting**: Argentina numbers use `format_phone_number()` in `webhook.py:43` (removes 9 prefix, inserts 15)
7. **Input sanitization**: `app/utils/sanitizer.py` strips SQL injection keywords, control chars, HTML tags
8. **LLM priority**: Gemini 2.5 Flash → OpenRouter → MiniMax in `llm_router.py`
9. **Rate limiter**: In-memory only (not Redis-backed)
10. **Dashboard SPA**: Built into multi-stage Dockerfile. `admin.py` serves CRUD endpoints at `/admin/*` using sync psycopg2 session. Nginx config in `dashboard/nginx.conf` proxies `/api/` → `app:8000`
11. **Dashboard dev**: `cd dashboard && npm install && npm run dev` — Vite proxies `/api` to `localhost:8000`
12. **No CI/CD, no pre-commit** — all checks manual

## Testing

- `pytest-asyncio` with `asyncio_mode = "auto"` (pyproject.toml:66)
- Tests in `tests/` — mock LLM, no DB required
- No integration test fixtures

## Deploy

- Render Blueprint via `render.yaml` — auto-deploy on push
- Multi-stage Dockerfile: Stage 1 builds dashboard SPA, Stage 2 runs Python
- CORS: `https://inmueblebot-api.onrender.com` + localhost origins
- Health: `GET /health`, `GET /health/redis`
- Dashboard served at `/dashboard` when `dashboard/dist/` exists
