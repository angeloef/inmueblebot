# InmuebleBot — Agent Guide

## Entrypoints

- **FastAPI app**: `app/main.py` — uvicorn entrypoint: `app.main:app`
- **Docker compose**: `docker compose up -d` (starts db, redis, app, streamlit UI)
- **Render deploy**: `render.yaml` — uses `env: docker` → `Dockerfile` (python:3.12-slim)

## Developer Commands

```bash
uvicorn app.main:app --reload              # Dev server (port 8000)
pytest tests/ -v                           # All tests
pytest tests/test_agent.py -v              # Single test file
ruff check app/ tests/                     # Lint (ruff config in pyproject.toml)
mypy app/                                  # Typecheck (mypy config in pyproject.toml)
pip install -r requirements.txt            # Install deps
```

**Order**: `ruff check .` → `mypy app/` → `pytest tests/ -v`

## Architecture

- **`app/agents/`** — LLM routers (Gemini, OpenRouter, MiniMax), prompts, tools, real_estate_agent
- **`app/api/routes/`** — Webhook (WhatsApp Meta), admin, internal
- **`app/core/`** — Config (pydantic-settings), memory, state machine, intent
- **`app/db/`** — SQLAlchemy async, models (User, Conversation, Message, Property, Appointment), migrations (alembic)
- **`app/services/`** — Property, appointment, calendar, lead, handoff, notification
- **`app/integrations/`** — WhatsApp (Meta + Twilio), Calendar (Google), Storage
- **`app/utils/`** — Sanitizer, rate_limiter (in-memory), date_parser, lang_detector, logger
- **`frontend/`** — Streamlit chat UI (port 8502)

## Critical Quirks

1. **DATABASE_URL must use asyncpg driver**: Render provides `postgresql://...` — config auto-converts to `postgresql+asyncpg://` via `resolved_database_url` property in `app/core/config.py:184`
2. **Python 3.14 breaks SQLAlchemy 2.0 ORM**: Render default is 3.14 — `runtime.txt` pins `python-3.12`. If Removed, ALL model type annotations must use `Optional[X]` not `X | None` syntax
3. **Model type annotations**: Use `Optional[str]`, `List[str]`, `Optional[Dict]` — NEVER `str | None`, `list[str]`, `dict` (triggers `TypeError: descriptor '__getitem__' requires a 'typing.Union' object`)
4. **JSON logging**: `loguru` configured with `serialize=True` in `app/main.py:28` — structured JSON for Render log streams
5. **WhatsApp phone formatting**: Argentina numbers need `format_phone_number()` in `webhook.py:43` (removes 9 prefix, inserts 15)
6. **Input sanitization**: All user input goes through `app/utils/sanitizer.py` — strips SQL injection keywords, control chars, HTML tags
7. **LLM priority**: Gemini 2.5 Flash (primary) → OpenRouter (backup) → MiniMax (last resort) — configured in `app/agents/llm_router.py`
8. **Rate limiter**: In-memory only (not Redis-backed) — `app/utils/rate_limiter.py`
9. **No CI/CD, no pre-commit, no GitHub workflows** — all validation is manual

## Testing

- `pytest-asyncio` with `asyncio_mode = "auto"` (set in `pyproject.toml:66`)
- Tests in `tests/` — mock LLM responses, no DB required for most
- No integration test fixtures for DB/Redis

## Deploy

- Render Blueprint via `render.yaml` — sync from Render Dashboard after pushing
- CORS restricted to `https://inmueblebot-api.onrender.com`
- Health check: `GET /health`
