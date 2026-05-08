# InmuebleBot — Senior Developer Context

> WhatsApp AI Real Estate Assistant | FastAPI + Multi-LLM + PostgreSQL + React Dashboard
> Target market: Argentina, Paraguay (Spanish/Portuguese speaking users)
> ~17,873 LOC across 55+ Python modules, 6 React JSX files

## Entrypoints

| Purpose | Command | Port |
|---------|---------|------|
| Dev API server | `uvicorn app.main:app --reload` | 8000 |
| Docker full stack | `docker compose up -d` | 8000 (API), 8502 (Streamlit), 3000 (Dashboard Vite) |
| Dashboard dev | `cd dashboard && npm run dev` | 5173 |
| Dashboard build | `cd dashboard && npm run build` | → `dashboard/dist/` |
| Run tests | `pytest tests/ -v` | — |
| Typecheck | `mypy app/` | — |

## Stack

- **Python 3.12+** with FastAPI + SQLAlchemy 2.0 async + asyncpg
- **PostgreSQL 16** (primary via Docker, Render managed externally)
- **Redis 7 Alpine** (session state, conversation context, classifier cache, rate limiting in-memory fallback)
- **LLM**: OpenAI GPT-4o-mini (single provider — friend's refactor replaced the multi-provider chain)
- **WhatsApp**: Meta Cloud API (v18.0 Graph API) → `facebook.com/v18.0/{phone_number_id}/messages`
- **Dashboard**: React SPA (Vite, @tanstack/react-query, axios)
- **Streamlit**: Legacy chat UI (`frontend/chat_ui.py`, port 8502)
- **Celery**: Background tasks (followups, lead scoring, reminders, maintenance)
- **Docker**: Multi-stage (dashboard build → Python runtime), deployed on Render via `render.yaml`
- **Linting**: ruff (strict), mypy (non-strict)

## Recent Changes (Claude Code — May 2026)

Three "nuclearizando al agente" commits refactored the core:

### Fase 0 — Housekeeping
- `.gitignore`: Added `*.sqlite` / `*.sqlite3` endings
- `storage.py` + `twilio.py`: Fixed import paths (`config.settings` → `app.core.config`)
- **Fixed** seed data wipe: `main.py` now always uses `force=False` — no more data loss on restart

### Fase 1 — Agent Rewrite + Webhook Improvements
- Added `_deterministic_dispatch()` method — replaces hacky keyword-match forced search with classifier-entity-based dispatch. When `PROPERTY_SEARCH` intent + slots complete, searches directly and uses LLM only for formatting.
- Added `entities` parameter to `process_turn()` — passes classifier-extracted slots to agent.
- Added `_sanitize_response_text()` leak detector — strips base64 data URIs, local paths, tool call artifacts from LLM output before sending.
- **Fixed** state machine race: Entire turn (classify + agent + save) now executes INSIDE the per-user Redis lock.
- Added image URL validation — validates URLs before sending via WhatsApp API.

### Fase 2 — Switched to GPT-4o-mini
- `llm_router.py`: Replaced multi-provider chain (Gemini → OpenRouter → MiniMax → Fallback) with single `AsyncOpenAI` using GPT-4o-mini. Much simpler, 561→174 lines.
- `classifier.py`: Replaced OpenRouter-based intent classifier with OpenAI using `response_format=json_object` for deterministic structured output. Removed fragile text parsing.
- `config.py`: Added `OPENAI_API_KEY` and `OPENAI_MODEL` (default: `gpt-4o-mini`). Old LLM keys marked as deprecated.
- `requirements.txt`: Added `openai>=1.30.0`.

### Open Issues (NOT Fixed)
| **Fixed** | seed data wipe, state machine race, forced search double-exec, switched to GPT-4o-mini | ✅ Fixed |
| **Fixed** | timezone bug (Argentina UTC-3), exception handlers, message loss on crash, Celery dead code, NFKD Spanish names, connection pool leaks | ✅ Fixed |
| **Remaining** | credential exposure (render.yaml/old.env), no auth on debug endpoints, no CI/CD, webhook signature verification | 🔴 Still open |

---

## Calendar System (Refactored May 8, 2026)

The calendar system uses a unified **America/Argentina/Buenos_Aires** timezone (GMT-3) across all layers:

- **`calendar_service.py`** — Refactored: dead code removed, `_parse_datetime` uses Buenos Aires timezone (not UTC). All 7 Google API calls use `_execute_async()` + `asyncio.to_thread()` for non-blocking async. OAuth token auto-refresh added.
- **`admin.py`** — Admin appointment CRUD endpoints now sync to Google Calendar. `calendar_event_id` stored/updated/removed on create/update/cancel.
- **`tools.py`** — `schedule_visit` checks Google Calendar availability with correct `property_id` type (int, not UUID).
- **`config.py`** — Added `CALENDAR_CREDENTIALS_DIR`, `CALENDAR_TOKEN_FILE`, `CALENDAR_CLIENT_SECRETS_FILE` config fields.
- **Dashboard** — Calendar UI shows real sync status. Uses `America/Argentina/Buenos_Aires` for timezone conversions. GMT-3 label displayed.

## Critical Architecture Notes

### 1. The Webhook Double-Prefix Bug
The webhook router is mounted at `/webhook` and route paths must NOT include `/webhook/`:
```python
# app/main.py
app.include_router(webhook_router, prefix="/webhook", tags=["whatsapp"])

# app/api/routes/webhook.py — WRONG (double prefix):
@router.post("/webhook/whatsapp")   # actual path: /webhook/webhook/whatsapp ✗
# RIGHT:
@router.post("/whatsapp")           # actual path: /webhook/whatsapp ✓
```

### 2. DATABASE_URL Must Use asyncpg
Auto-adds `+asyncpg` to plain `postgresql://` URLs in `config.py:resolve_database_url()`.
Render provides `postgresql://...` without driver prefix — the resolver handles it.
**Admin routes** use sync psycopg2; they strip `+asyncpg` from the URL in `_get_sync_session()`.

### 3. LLM Routing (single provider — refactored)
Now single provider: **OpenAI GPT-4o-mini** via `AsyncOpenAI` (no more multi-provider chain).
- Uses _provider_health dict + _rate_limit_until cooldowns (60s on 429)
- Retries per provider: up to 3 attempts with exponential backoff
- When Gemini 400s with tools, retries without tools before falling through
- Each provider maintains health status; unhealthy providers are skipped

### 4. Agent Tool Calling with Forced Search
The agent in `real_estate_agent.py` has a **forced search** bypass: if the user message contains clear search intent keywords (busco, quiero, casa, departamento, etc.), it calls `search_properties` directly on iteration 0 without waiting for the LLM to decide. This is a performance optimization that can race with the LLM's own tool decisions.

### 5. Property ID System (Dual ID)
The `Property` model uses an **integer primary key** (seeded from JSON data, `autoincrement=False`). The `original_id` field mirrors it for backward compatibility. Tools (`tools.py`) try integer lookup first, then UUID, then title search. This creates ambiguity in `get_property_details` and `schedule_visit` where both int and UUID lookups happen.

### 6. Memory Architecture (Dual Store)
- **Redis** (short-term): user context (state, last search, pending_scheduling), last 20 messages, intent cache (5 min TTL)
- **PostgreSQL** (long-term): user preferences, lead score, conversation history
- On Redis failure, falls back to empty defaults (graceful degradation)

### 7. State Machine (Conversation Flow)
States: `idle` → `qualifying` → `searching` → `viewing_property` → `booking` → `completed` / `handoff`
- Stored in Redis with 30-min TTL per user
- State transitions validated; `allow_invalid=True` in agent overrides the check

### 8. WhatsApp Phone Number Formatting (Argentina)
`format_phone_number()` in `webhook.py:80`:
- Strips `+`
- Removes `9` after country code `54` (Argentina mobile prefix)
- Inserts `15` after area code
- E.g., `+54375415532056` or `+549375415532056` → `54375415532056`

### 9. Dashboard SPA Serving
Served from `dashboard/dist/` when available. Multi-stage Docker builds it automatically.
The admin routes (`/admin/*`) are served by FastAPI using sync psycopg2 (lazy-initialized engine).
The dashboard Nginx config is at `dashboard/nginx.conf`.

### 10. LLM Intent Classifier Is Not Gemini
The `intent_classifier` in `classifier.py` uses OpenRouter (NOT Gemini) with temperature=0.
Results cached in Redis for 5 minutes. Falls back to `UNKNOWN` on error.

## File Layout (Key Files)

```
inmueblebot/
├── app/
│   ├── main.py                          # FastAPI app, lifespan, CORS, routers, dashboard SPA
│   ├── agents/
│   │   ├── real_estate_agent.py          # Main agent: turn processing, tool loop, forced search
│   │   ├── llm_router.py                 # Multi-LLM router with fallback chain
│   │   ├── tools.py                      # Tool implementations (~994 lines, 13 tools)
│   │   ├── prompts.py                    # System prompt + few-shot examples (~1029 lines)
│   │   ├── gemini_client.py              # Gemini 2.5 Flash adapter
│   │   ├── openrouter_client.py          # OpenRouter adapter
│   │   └── llm.py                        # MiniMax adapter (AsyncMiniMaxClient)
│   ├── core/
│   │   ├── config.py                     # Pydantic-settings, multi-source .env loading
│   │   ├── state_machine.py              # Redis-backed FSM for conversation flow
│   │   ├── memory.py                     # Hybrid memory (Redis + PostgreSQL), ~695 lines
│   │   ├── classifier.py                 # OpenRouter-based intent classifier
│   │   ├── intent.py                     # Intent enum (7 intents)
│   │   ├── date_parser.py                # Spanish date/time parsing
│   │   ├── session.py                    # Session management
│   │   └── router.py                     # Simple router (legacy)
│   ├── api/routes/
│   │   ├── webhook.py                    # WhatsApp webhook handler (~408 lines)
│   │   ├── admin.py                      # Admin CRUD API (sync psycopg2, ~680 lines)
│   │   └── internal.py                   # Internal endpoints
│   ├── db/
│   │   ├── models/
│   │   │   ├── property.py               # Property model (integer PK, JSONB extras)
│   │   │   ├── user.py                   # User/Lead model (UUID PK, JSONB prefs)
│   │   │   ├── appointment.py            # Appointment model (UUID PK, FK constraints)
│   │   │   ├── conversation.py           # Conversation model
│   │   │   └── message.py                # Message model
│   │   ├── repository.py                 # Generic + User/Property/Appointment repos
│   │   ├── session.py                    # async_session_factory
│   │   ├── seed.py                       # Seeds from tests/obera_properties.json
│   │   ├── create_tables.py              # Auto-create tables at startup
│   │   └── base.py                       # SQLAlchemy declarative base
│   ├── services/
│   │   ├── property_service.py           # Advanced property search (~428 lines)
│   │   ├── appointment_service.py        # Appointment CRUD + Google Calendar (~565 lines)
│   │   ├── calendar_service.py           # Google Calendar integration
│   │   ├── handoff_service.py            # Human handoff/escalation
│   │   ├── lead_service.py               # Lead management
│   │   ├── notification_service.py       # Notifications
│   │   └── followup_service.py           # Follow-ups
│   ├── integrations/
│   │   ├── whatsapp.py                   # Meta Cloud API client (send_message, image, buttons, templates)
│   │   ├── twilio.py                     # Twilio integration (legacy)
│   │   ├── calendar.py                   # Calendar integration
│   │   └── storage.py                    # File storage
│   ├── tasks/
│   │   ├── followups.py                  # Celery followup tasks
│   │   ├── lead_scoring.py               # Lead scoring batch jobs
│   │   ├── maintenance.py                # DB maintenance
│   │   └── reminders.py                  # Appointment reminders
│   └── utils/
│       ├── sanitizer.py                  # Input sanitization (SQLi, HTML, control chars)
│       ├── date_parser.py                # Spanish/Portugese date parser
│       ├── lang_detector.py              # Language detection (es/pt)
│       ├── rate_limiter.py               # In-memory rate limiter
│       └── logger.py                     # Loguru JSON logger
├── config/
├── celery_app.py                        # Celery app (REMOVED - dead code, May 8)
├── config/
│   └── settings.py                       # App settings
├── dashboard/
│   ├── src/                              # React app (~1,630 LOC)
│   │   ├── Dashboard.jsx                 # Main dashboard view
│   │   ├── Properties.jsx                # Property management view
│   │   ├── Calendar.jsx                  # Calendar view with appointments
│   │   ├── Clients.jsx                   # Lead management
│   │   ├── Shell.jsx                     # App shell/layout
│   │   ├── Primitive.jsx                 # Shared components
│   │   ├── EventPopover.jsx              # Appointment popover
│   │   ├── api.js                        # Axios API client
│   │   └── data.jsx                      # Data utilities
│   ├── styles.css                        # Global styles
│   ├── tokens.css                        # Design tokens
│   └── nginx.conf                        # Production Nginx config
├── frontend/
│   └── chat_ui.py                        # Streamlit chat UI (legacy, port 8502)
├── scripts/
│   ├── authenticate_calendar.py          # Google Calendar OAuth setup
│   ├── test_calendar.py                  # Calendar integration test
│   └── seed_db.py                        # DB seeding script
├── tests/
│   ├── test_agent.py                     # Agent integration tests
│   ├── test_llm_router.py                # LLM router tests
│   ├── test_memory.py                    # Memory tests
│   ├── test_memory_integration.py        # Memory integration tests
│   ├── test_router.py                    # Router tests
│   ├── test_router_examples.py           # Router example tests
│   ├── test_phase2.py                    # Phase 2 feature tests
│   ├── test_intent.py                    # Intent classification tests
│   ├── test_tasks.py                     # Celery task tests
│   ├── test_property_service.py          # Property service tests
│   ├── test_appointment_service.py       # Appointment service tests
│   ├── test_handoff.py                   # Handoff tests
│   └── obera_properties.json             # Seed data (50+ properties)
├── Dockerfile                            # Multi-stage build
├── docker-compose.yml                    # Full stack (db, redis, app, streamlit, dashboard)
├── render.yaml                           # Render Blueprint config
├── alembic/                              # DB migrations (not actively used)
└── .env.example                          # All config variables documented
```

## Developer Commands

```bash
# Dev server
uvicorn app.main:app --reload

# Full stack
docker compose up -d

# Dashboard only
cd dashboard && npm install && npm run dev

# Tests
pytest tests/ -v
pytest tests/test_agent.py -v -k "test_name"

# Lint + Typecheck
ruff check app/ tests/
mypy app/

# Docker build
docker compose build app

# Seed database
python -c "import asyncio; from app.db.seed import seed_properties; asyncio.run(seed_properties(force=True))"
```

## Python Dependencies (requirements.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115.0 | Web framework |
| uvicorn | 0.32.0 | ASGI server |
| sqlalchemy | 2.0.36 | ORM (async) |
| asyncpg | 0.30.0 | PostgreSQL async driver |
| psycopg2-binary | 2.9.9 | Sync driver for admin |
| redis | 5.2.0 | Cache + session state |
| httpx | 0.27.2 | Async HTTP client |
| google-genai | 1.0.0 | Gemini SDK |
| google-api-python-client | 2.100.0 | Google Calendar |
| loguru | 0.7.0 | Structured logging |
| celery | 5.4.0 | Background tasks |
| streamlit | 1.40.0 | Legacy chat UI |
| pydantic-settings | 2.6.0 | Config management |
| alembic | 1.14.0 | DB migrations |
| ruff | 0.8.0 | Linter |
| mypy | 1.14.0 | Type checker |
| pytest | 8.3.0 | Test runner |

## Configuration (.env)

Three sources in priority order:
1. System environment variables (Render Dashboard)
2. `/etc/secrets/.env` (Render Secret Files — production)
3. `.env` (local development)

Key variables:
- **LLM**: `GEMINI_API_KEY` + `GEMINI_MODEL`, `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`, `MINIMAX_API_KEY`
- **WhatsApp**: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
- **DB**: `DATABASE_URL` (auto-adds `+asyncpg`)
- **Redis**: `REDIS_URL` or `USE_LOCAL_REDIS=true`
- **Security**: `ADMIN_API_KEY`, `SECRET_KEY`
- **Env**: `ENVIRONMENT` (development/production)

## Common Patterns & Pitfalls

### Tool Registration
Tools are defined as async functions in `tools.py` and registered in `TOOL_FUNCTIONS` dict (line 910). Each tool also needs a JSON schema definition in the system prompt (not a separate registry — schemas are in the prompts.py inline definitions or in the user-facing prompt text). The schema loading for OpenRouter uses a different format than Gemini.

### The Agent Loop (real_estate_agent.py)
```
1. Load user context from Redis + Redis message history (last 10)
2. Check for handoff intent → early return
3. Build messages: system prompt + context injection + conversation history
4. Forced search bypass on iteration 0 if clear search intent detected
5. LLM call → tool execution → append results → loop (max 3 iterations)
6. Update state machine + lead score + preferences
7. Clean response text (remove debug/programming words)
8. Return structured result
```

### Context Injection for Property References
The agent injects `<last_results>` XML tags with explicit mapping of option numbers to database IDs to prevent LLM hallucination of property IDs. The mapping format is:
```
<opción 1> → ID=prop-001 | Casa amplia | $180,000 | 4 hab | Posadas
```

### Image Handling
Images are passed via `<!--IMAGES:[...]-->` HTML comments in tool results and extracted by `_extract_rich_content()`. The `format_property_list()` function collects up to 3 images per property, deduplicates, and limits to 6 total. Images are sent to WhatsApp after the text response.

### Appointment Confirmation
The `schedule_visit` tool embeds confirmed time in `<!--CONFIRMED:YYYY-MM-DD HH:MM-->` comment. The system prompt explicitly instructs the LLM to use this exact time (not what the user said) in the confirmation message.

### Google Calendar Integration
The appointment service checks Google Calendar availability before creating appointments. On conflict, returns alternative time suggestions. OAuth setup is in `scripts/authenticate_calendar.py`.

### Celery Tasks
Four task types in `app/tasks/`:
- `followups.py` — Follow-up messages to leads
- `lead_scoring.py` — Batch lead score recalculation
- `maintenance.py` — DB maintenance (vacuum, reindex)
- `reminders.py` — Appointment reminder messages

### Admin API (sync psycopg2)
The admin routes at `/admin/*` use a separate synchronous SQLAlchemy session with psycopg2. The engine is lazy-initialized on first request. A `_run_startup_migration()` function runs idempotent ALTER TABLE migrations on first connection. API-key auth via `x-api-key` or `x-admin-api-key` header.

### Rate Limiting
- In-memory per-user: 1 second between messages from same phone (webhook.py)
- Message dedup: 5-minute TTL on message IDs (webhook.py)
- LLM provider: 60s cooldown on 429 rate limit (llm_router.py)
- Redis connection: exponential backoff, 3-5 retries, then degraded mode

### Input Sanitization
All user inputs are sanitized via `app/utils/sanitizer.py`:
- SQL injection keywords stripped
- HTML tags stripped
- Control characters stripped
- Property IDs validated (no SQL injection in numeric ID paths)
- Separate sanitizers for: text, phone, property_id, criteria, date, time

## Test Patterns

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` (set in pyproject.toml).
No DB fixtures — tests mock LLM calls and Redis. 
Key test files and their focus:
- `test_agent.py` — End-to-end agent conversation flows
- `test_llm_router.py` — Provider fallback logic
- `test_memory.py` + `test_memory_integration.py` — Redis + PostgreSQL memory
- `test_router.py` — Intent routing
- `test_property_service.py` — Property search/filter logic
- `test_appointment_service.py` — Appointment CRUD + conflict detection
- `test_intent.py` — Intent classification

## Deployment (Render)

- Blueprint: `render.yaml` with `env: docker`
- Auto-deploys on push (Render Blueprint detected via `render.yaml`)
- Multi-stage Docker ensures dashboard SPA is built before Python runtime
- Health check: `GET /health` (checks Redis), `GET /health/redis`
- CORS allows: `https://inmueblebot-api.onrender.com`, localhost:5173:3000:8051
- No CI/CD pipeline defined — all checks manual

## Dashboard API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /admin/leads | x-api-key | List leads |
| GET | /admin/leads/:id | x-api-key | Get lead |
| POST | /admin/leads | x-api-key | Create lead |
| PATCH | /admin/leads/:id | x-api-key | Update lead |
| DELETE | /admin/leads/:id | x-api-key | Delete lead |
| GET | /admin/properties | x-api-key | List properties |
| POST | /admin/properties | x-api-key | Create property |
| PATCH | /admin/properties/:id | x-api-key | Update property |
| DELETE | /admin/properties/:id | x-api-key | Soft-delete property |
| GET | /admin/appointments | x-api-key | List appointments |
| POST | /admin/appointments | x-api-key | Create appointment |
| PATCH | /admin/appointments/:id | x-api-key | Update appointment |
| DELETE | /admin/appointments/:id | x-api-key | Delete appointment |
| GET | /admin/handoffs | x-api-key | List handoffs |

## Known Issues & Technical Debt

1. **No pre-commit hooks or CI** — ruff/mypy/pytest must be run manually
2. **Database engine creation per request** — services create engines on the fly instead of using the global async_session_factory, causing connection churn (property_service.py, tools.py, memory.py all create ad-hoc engines)
3. **Streamlit duplicates the chat UI** — `frontend/chat_ui.py` directly calls the LLM without going through the agent (no tools, no state machine)
4. **Celery broker not configured** — tasks defined but likely don't run without Redis broker config
5. **Seed data loads every startup in development** — `lifespan` calls `seed_properties(force=True)` in dev mode, which could reset manual edits
6. **OpenRouter model comment uses Nemotron but code says Grok** — `llm_router.py` docstring mentions Grok, `.env.example` uses `openai/gpt-oss-120b:free`
7. **Duplicate line in classifier** — `classifier.py:253-254` has duplicate `return data["choices"][0]["message"]["content"]`
8. **No typing in agents** — `real_estate_agent.py` `_extract_rich_content` and many methods omit return types
9. **Hardcoded locations** — lists of cities/locations hardcoded across tools.py, memory.py, real_estate_agent.py
10. **Admin mutations don't sync to bot** — changes made via admin API won't refresh Redis state machine context
11. **No Redis Sentinel/Cluster support** — single Redis instance, no HA
12. **Property integer PK collision risk** — `_next_property_id()` in admin.py does `MAX(id) + 1`, race condition on concurrent creates

## LLM Tools Reference

**13 tools** defined in `tools.py`:

| Tool | Parameters | Purpose |
|------|-----------|---------|
| `search_properties` | criteria dict (location, budget_min/max, bedrooms, bathrooms, property_type, operation_type, limit) | Main search |
| `get_property_details` | property_id (int, UUID, or title) | Property details |
| `recommend_properties` | user_preferences dict | Preference-based recommendations |
| `update_user_preferences` | phone, location, budget_max/min, property_type, operation_type, bedrooms | Save prefs |
| `get_user_preferences` | phone | Read saved prefs |
| `save_lead_info` | phone, name, email, budget, notes | Save lead info |
| `schedule_visit` | property_id, date_str, time_str, phone | Schedule visit |
| `reschedule_appointment` | appointment_id, new_date_str, new_time_str, phone | Reschedule |
| `cancel_appointment` | appointment_id, reason, phone | Cancel |
| `get_my_appointments` | phone | List appointments |
| `request_human_assistance` | phone, reason | Escalate to human |
| `refine_search` | refinement, previous_criteria | Narrow results |
| `get_property_images` | property_id | Get property images |
