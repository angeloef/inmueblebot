# InmuebleBot — Senior Developer Context

> WhatsApp AI Real Estate Assistant | FastAPI + Multi-LLM + PostgreSQL + React Dashboard
> Target market: Argentina, Paraguay (Spanish/Portuguese speaking users)
> ~17,873 LOC across 55+ Python modules, 6 React JSX files

## ⚠️ TOP PRIORITY — Database & Redis Migration TESTED ✅

The migration from Frankfurt (EU) to Oregon (US West) has been completed and tested. All column rename issues fixed via auto-migrations.
Critical fixes applied: see Sprint 9-12 below.

### Quick Test Scenarios (Run After Deploy)
```bash
# 1. Verify properties load in dashboard at /admin/properties
# 2. Verify appointments load in dashboard at /admin/appointments
# 3. Send a WhatsApp message → check logs for DB or Redis errors
# 4. Search for a property → verify LLM response includes results
# 5. Schedule a visit → verify appointment created + Calendar event
# 6. Open Dashboard → verify data loads at /admin/leads, /admin/appointments
```

---

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
- **PostgreSQL 16** (Render Managed, **Oregon** region — migrated from Frankfurt May 10 — ⚠️ UNTESTED, see TOP PRIORITY)
- **Redis 7 Alpine** (Render Managed, **Oregon** region — recreated May 10, auto-injected via blueprint — ⚠️ UNTESTED, see TOP PRIORITY)
- **LLM**: OpenAI GPT-4o-mini (single provider — friend's refactor replaced the multi-provider chain)
- **WhatsApp**: Meta Cloud API (v18.0 Graph API) → `facebook.com/v18.0/{phone_number_id}/messages`
- **Dashboard**: React SPA (Vite, @tanstack/react-query, axios)
- **Streamlit**: Legacy chat UI (`frontend/chat_ui.py`, port 8502)
- **Celery**: Background tasks (followups, lead scoring, reminders, maintenance)
- **Docker**: Multi-stage (dashboard build → Python runtime), deployed on Render via `render.yaml`
- **Linting**: ruff (strict), mypy (non-strict)

## Recent Changes (Hermes Agent — May 2026)

The codebase underwent a comprehensive 3-phase architecture sprint following initial bug-fix sprints.

### Sprint 1 — Bug Fixes (May 8, 2026)

| Issue | Severity | Fix |
|-------|----------|-----|
| **Timezone (appointments 3h off)** | 🔴 CRITICAL | `_ensure_timezone()` now uses `America/Argentina/Buenos_Aires` via `pytz.localize()` instead of `dt.replace(tzinfo=tz.utc)` |
| **No exception handlers** | 🔴 CRITICAL | Added `@app.exception_handler(Exception)` with structured logging |
| **Webhook message loss on crash** | 🟠 HIGH | Wrapped `process_messages()` in try/except |
| **Celery dead code** | 🔴 CRITICAL | Removed entirely (Celery, tasks/, deps/, celery_settings.py) |
| **NFKD destroys Spanish names** | 🟡 MEDIUM | Removed `unicodedata.normalize('NFKD', text)` from sanitizer |
| **Connection pool leak** | 🟠 HIGH | `engine.dispose()` moved before `return` in property_service |
| **Calendar refactor** | 🟠 HIGH | Dead code removed, timezone unified to Buenos Aires, all API calls async, OAuth refresh added, admin CRUD syncs to Google Calendar |
| **WhatsApp image sending** | 🟠 HIGH | 4 bugs: silent failure in send_image, localhost URLs, no rate-limiting, hardcoded URLs |

### Sprint 2 — Context Memory + Temporal Reasoning (May 9, 2026)

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| **Property context lost after 3-4 turns** | `selected_property_id` existed in Redis schema but was NEVER written to | Now saved after `get_property_details`/`get_property_images` and injected into LLM context |
| **Pending scheduling info ignored** | `pending_scheduling_info` was saved to Redis but NEVER loaded into LLM context | Now injected via `_build_messages()` system message |
| **"próximo martes" parsed as "martes"** | Simple weekday match ran BEFORE weekday_patterns regex | Reordered: weekday_patterns first, simple weekday as fallback |
| **Bot contradicts user dates** | Prompt lacked rules against contradicting | Added `PROPIEDAD ACTIVA` + `CONSISTENCIA TEMPORAL` sections to system prompt |

### Sprint 3 — 3-Phase Architecture Refactor (May 9-10, 2026)

#### Phase 0 — Housekeeping
- **Provider cleanup**: Removed 6 legacy LLM keys from `config.py` (Gemini, OpenRouter, MiniMax). Only `OPENAI_API_KEY` remains
- **render.yaml**: Added `OPENAI_API_KEY` as `sync: false`
- **Token logging**: Added per-call + cumulative token usage logging for cost monitoring
- **MAX_TOOL_CALLS**: Increased from 3 to 5 with loop detection
- **Legacy client safety**: 3 deprecated provider files updated with `getattr` fallbacks

#### Phase 1 — Prompt + Tool Calling
- **System prompt**: Reduced from ~1064→~599 lines. Extracted few-shot examples as separate messages, consolidated all NUNCA rules into 5 compact REGLAS DE ORO, removed inline redundant examples
- **Forced search eliminated**: The keyword-based `is_clear_search` bypass was removed. LLM tool calling is now the ONLY path for search detection
- **Context injection reordered**: `selected_property_id`, `pending_scheduling_info`, and `last_shown_properties` are now injected BEFORE history messages

#### Phase 2 — Performance + Infrastructure
- **Global session pool**: Replaced 8 ad-hoc `create_async_engine()` + `dispose()` patterns across 5 files with global `async_session_factory` from `session.py`
- **Rate limiting**: New `app/core/rate_limiter.py` — Redis-based token bucket, 50 RPM global, graceful degradation when Redis is down
- **Memory fallback**: In-memory dict fallback (`_fallback_context`, `_fallback_messages`) when Redis is unavailable — users no longer lose conversation context on Redis restart

### Sprint 4 — Google Calendar Auth + Render Secrets (May 10, 2026)

- **Secure credential loading**: Added `/etc/secrets/` path resolution for Render Secret Files. Added env var-based credential loading (`GOOGLE_TOKEN_JSON`, `GOOGLE_CREDENTIALS_JSON`)
- **Service resilience**: Added `reset()` method, `_auth_failed` flag to prevent repeated retries on `invalid_grant`, better operator logging, user-facing "calendar sync unavailable" messaging
- **Read-only filesystem fix**: OAuth token refresh can't save to `/etc/secrets/` (Render mounts as read-only) — wrapped `_save_token()` in try/except with graceful degradation
- **New config fields**: `GOOGLE_TOKEN_JSON`, `GOOGLE_CREDENTIALS_JSON` in config.py
- **render.yaml**: Added both env vars with `sync: false`

### Sprint 5 — Appointment Rescheduling Fixes (May 10, 2026)

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| **Confirmation shows UTC time (3h off)** | `format_appointment_confirmation()` used `strftime` directly on UTC datetime from asyncpg | Convert to `America/Argentina/Buenos_Aires` via `astimezone()` before formatting |
| **Reschedule time stamped as UTC** | `reschedule_appointment_tool()` used `tzinfo=timezone.utc` for new time | Now uses `pytz.localize()` with Argentina timezone |
| **LLM hallucinates appointment ID** | LLM calls `reschedule_appointment(id='abc-123')` — completely fake UUID | Tool now auto-resolves: if UUID invalid, fetches user's most recent appointment by phone |
| **LLM invents date/time during reschedule** | No context about existing appointment in LLM messages | Injects `### CITAS EXISTENTES DEL USUARIO` with formatted appointment data + DB-first instruction |
| **Success response replaced by generic error** | Loop detector broke inner loop only; response_text stayed empty | Loop detector now detects scheduling tool success and breaks BOTH loops, using success message |
| **"a las 7" interpreted as 07:00 not 19:00** | No contextual hour interpretation | Tool adds +12h when existing appointment is PM and user says hour < 12 |
| **Wrong date when only time changes** | LLM sends `2026-05-19` instead of original date | Prompt rule: "SI EL USUARIO SOLO MENCIONA UNA NUEVA HORA, NO CAMBIES LA FECHA" |
| **property_type PostgreSQL type mismatch** | Column is `character varying[]` but code sent JSON serialized array | `cast(prop_type, ARRAY(String))` from SQLAlchemy |
| **ll (encoding corruption in "mañana")** | `sanitize_date_input()` regex whitelist didn't include `ñ` | Added `ñáéíóúü` to the whitelist |

### Sprint 6 — Error Handling + Production Safeguards (May 10, 2026)

- **Internal error detection**: New `is_internal_error()` in `sanitizer.py` — detects 20+ patterns (property ID errors, DB errors, SQLAlchemy traces, Python exceptions)
- **Safe user-facing fallback**: When internal error detected, response is replaced with: *"Perdón, ocurrió un inconveniente al procesar la información de la propiedad. Un asesor humano se contactará con vos a la brevedad."*
- **LLM date hallucination guard**: In `schedule_visit`, when validation fails on a NUMERIC date (DD/MM/YYYY), returns message telling LLM to pass raw text
- **Anti-hallucination property ID guard**: 3 tools (get_property_details, get_property_images, schedule_visit) now validate property_id is numeric or UUID before proceeding. Invalid IDs like `abc-123` are caught early with a corrective message to the LLM
- **Few-shot examples fixed**: Changed `prop-001` → `1` in all examples — was training LLM to use wrong ID format
- **Context injection reordered**: `existing_appointments` now injected BEFORE conversation history

### Sprint 7 — Smart Search + Location Matching (May 10, 2026)

- **normalize_location()**: New function in `sanitizer.py` — strips street prefixes (calle, av, avenida, pasaje, boulevard) and trailing street numbers. `"Calle Sarmiento 285"` → `"sarmiento"`
- **Fuzzy ILIKE search**: `repository.py:search()` now uses 3-strategy OR combination: (1) original query, (2) normalized (prefix stripped), (3) individual words OR'd

### Sprint 8 — Latency Optimizations (May 10, 2026)

| Optimization | Files Changed | Measured Impact |
|-------------|--------------|-----------------|
| **Prompt reduction**: History 10→5 messages, compressed property context (id+title only), few-shot examples inlined into SYSTEM_PROMPT | `real_estate_agent.py`, `prompts.py` | ~2,900 fewer prompt tokens per LLM call (from 4,800→1,900) |
| **Short-circuit LLM iterations**: schedule_visit/reschedule/cancel with confirmation → use tool result directly, skip iteration 2 | `real_estate_agent.py` | 2→1 LLM calls on scheduling (~50% reduction, saves ~1.5s) |
| **Parallel post-agent saves**: State machine, lead score, preferences now run via `asyncio.gather()` | `real_estate_agent.py` | Post-processing ~4-5s→1-2s |
| **Calendar OAuth pre-warm**: Service initialized at startup via `calendar_service.service` access in `lifespan()` | `main.py` | Eliminates 2s cold start on first appointment |
| **Response time logging**: `[Timing] phone=XXXX total=3.45s` logged per webhook | `webhook.py` | New observability |
| **DD/MM/YYYY + natural language dates**: 3-stage parsing in reschedule (YYYY-MM-DD → DD/MM/YYYY → parse_spanish_datetime) | `tools.py` | Fixes infinite reschedule loop |
| **Reschedule retry limit**: Max 2 consecutive failures, then breaks with friendly message | `real_estate_agent.py` | Prevents infinite loop |

**Latency validation (from production logs):**

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| Schedule visit | ~14s, 2 LLM calls | ~7s, **1 LLM call** | **−50%** |
| Search | ~12s | ~8s | **−33%** |
| Generic reply | ~6s | ~3-4s | **−33%** |
| Tokens per turn | ~19K | ~3.3K (scheduling) | **−83%** |

### Sprint 9 — Infrastructure Migration (May 10, 2026)

The API was already on Render Oregon, but both PostgreSQL and Redis were in **Frankfurt** — adding ~500ms round-trip latency per operation.

| Change | Method | Result |
|--------|--------|--------|
| **PostgreSQL** Frankfurt → Oregon | pg_dump → Render API create → psql restore + column rename | DB now at `dpg-d7vet8tckfvc73ehnjk0-a.oregon-postgres.render.com` |
| **Redis** Frankfurt → Oregon | Render API create (`POST /v1/redis`) | Now at `red-d7vfg9d0lvsc73fqmg60.oregon-keyvalue.render.com` |
| **render.yaml** Redis service | Re-added with `plan: free`, `region: oregon` | REDIS_URL auto-injected by Render blueprint |
| **render.yaml** credentials | Removed stale Frankfurt credentials | Oregon DB password + auto-injected Redis |

**⚠️ STATUS: TESTED AND FIXED** — All column rename issues identified and fixed via auto-migrations in `admin.py:_run_startup_migration()`. See Sprint 11 for details.

**Known deploy issue (env var wipe)**: The `PUT /v1/services/{id}/env-vars` Render API endpoint REPLACES all env vars, not just the specified key. When setting `REDIS_URL` via API, all other env vars (`DATABASE_URL`, `PORT`, `ENVIRONMENT`, etc.) were accidentally deleted. They were restored immediately. `OPENAI_API_KEY`, `GOOGLE_TOKEN_JSON`, and `GOOGLE_CREDENTIALS_JSON` are stored as Secret Files (`/etc/secrets/`) and were NOT affected.

### Sprint 10 — Rescheduling Robustness (May 10, 2026)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| **LLM passes `UUID_DE_LA_CITA` placeholder** | Prompt doesn't reinforce real UUID format | Added prompt rule: "usá el UUID exacto de la lista de CITAS EXISTENTES" |
| **`new_date_str='12/05/2026'` breaks strptime** | Tool expects `%Y-%m-%d` but LLM sends DD/MM/YYYY | 3-stage parsing: try `%Y-%m-%d`, then `%d/%m/%Y`, then `parse_spanish_datetime()` |
| **`new_date_str='mañana'` causes ValueError** | Natural language not handled by strptime | Falls through to `parse_spanish_datetime()` which handles "mañana", "próximo martes", etc. |
| **Infinite reschedule loop on failure** | No retry limit; LLM retries with same failing args | Max 2 consecutive failures → friendly message + loop break |
| **User says "a las 3 es muy temprano" but apt is at 17:00** | No contradiction detection | Prompt rule: "Si el usuario contradice la cita real, corregilo amablemente" + always fetch appointment from DB |

### Sprint 11 — Migration Fallout Fixes (May 10, 2026)

All column rename issues from Frankfurt→Oregon migration. Auto-migration DO blocks added to `admin.py:_run_startup_migration()`:

| # | Column | Action | Trigger |
|---|--------|--------|---------|
| 1 | `properties.operation_type` → `type` | ALTER RENAME | IF EXISTS on information_schema |
| 2 | `properties.property_type` → `extra_data['building_type']` | UPDATE + DROP | IF EXISTS |
| 3 | `properties.images` VARCHAR(255)[] → TEXT[] | ALTER TYPE | udt_name = '_varchar' |
| 4 | `properties.latitude` → `lat` | ALTER RENAME | IF EXISTS |
| 5 | `properties.longitude` → `lng` | ALTER RENAME | IF EXISTS |
| 6 | `properties.total_area` → `area_m2` | ALTER RENAME | IF EXISTS |
| 7 | `properties.extra_data` TEXT → JSONB | ALTER TYPE | udt_name = 'text' (run before city migration) |
| 8 | `properties.city` → `extra_data['city']` | UPDATE + DROP | IF EXISTS |
| 9 | `appointments.appointment_type` → `type` | ALTER RENAME | IF EXISTS |

**Also added:** `scripts/seed_oregon_properties.py` — 9 recovered properties with old→new column mapping, idempotent.

### Sprint 12 — Dashboard + Search Fixes (May 10, 2026)

| Issue | Fix | Files |
|-------|-----|-------|
| **Dashboard "add property" returned 500** | Fixed column renames + images type | `admin.py:_run_startup_migration()` |
| **Dashboard properties not found by WhatsApp bot** | Added `city` field to PropertyCreate schema + auto-append city to location | `admin.py`, `api.js`, `Properties.jsx` |
| **Stale Redis context biases test conversations** | Added `reset_user_context(phone)` to MemoryManager + `POST /admin/users/{phone}/reset` endpoint + auto-reset on startup for test phone `5493754455340` | `memory.py`, `admin.py`, `main.py` |
| **`<!--CONFIRMED:...-->` leaks to WhatsApp** | Added CONFIRMED pattern to `_OUTPUT_LEAK_PATTERNS` in sanitizer | `sanitizer.py` |
| **Reschedule says "Cita Agendada" instead of "Cita Reprogramada"** | Added `action_type='new'|'reschedule'` param to `format_appointment_confirmation()` | `appointment_service.py`, `tools.py` |

### Open Issues (NOT Fixed)

| Issue | Severity | Status |
|-------|----------|--------|
| Credential exposure (render.yaml hardcoded DB/Redis passwords) | 🔴 CRITICAL | Need rotation |
| No auth on `/admin/debug/users` and `/webhook/debug` | 🔴 CRITICAL | Still open |
| No CI/CD pipeline | 🔴 CRITICAL | Still open |
| Webhook signature verification skipped | 🔴 CRITICAL | Still open |
| Docker healthcheck uses curl (not in slim image) | 🟠 HIGH | Still open |
| Loguru `serialize=True` incompatible with Render log aggregation | 🟡 MEDIUM | Still open |
| No Redis Sentinel/Cluster support | 🟡 MEDIUM | Single instance, no HA |
| Streamlit duplicates chat UI without agent pipeline | 🟡 MEDIUM | Direct LLM call, no tools |
| Celery broker not configured | 🟡 MEDIUM | Tasks defined but don't run |
| Admin mutations via dashboard create proper city+location mapping | 🟡 MEDIUM | Fixed in Sprint 12 — now auto-appends city to location |
### 12. Cross-Region Latency (FIXED — May 10, 2026)
**Before**: DB in Frankfurt + Redis in Frankfurt → API in Oregon = ~500ms RTT per operation
**After**: All three services co-located in **Oregon** → ~1ms RTT per operation
**Impact**: ~4s saved per user message (8-10 DB queries × ~500ms eliminated)
**Method**: pg_dump → Render API (create new DB + Redis in Oregon) → restore → render.yaml update

### 13. LLM Token Bloat (Reduced — Sprint B1)
**Before**: ~4,800 prompt tokens per call, 2 calls per turn = ~19K tokens/turn
**After**: ~3,300 prompt tokens per call, 1 call for scheduling = ~3.3K tokens/turn (scheduling)

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

### 3. LLM Routing (single provider — OpenAI GPT-4o-mini)
Single provider: **OpenAI GPT-4o-mini** via `AsyncOpenAI`. No more multi-provider fallback chain.
- Retries: up to 3 attempts with exponential backoff on 429/5xx
- Rate limiting: Redis-based token bucket (50 RPM global)
- Token logging: per-call + cumulative for cost tracking
- Temperature: currently 0.7 (consider 0.3 for tool decisions)

### 4. Tool Calling (no forced search, loop detection)
The forced search bypass (keyword-based `is_clear_search`) was **removed** in Sprint 3. LLM tool calling is now the only path for search intent detection. The agent iterates up to 5 tool calls per turn with loop detection:
- If same tool called twice consecutively → inner break + check if success message exists
- If scheduling tool succeeded (`Cita Agendada`, `Cita Reprogramada`, `Confirmado`) → use success response, break outer loop
- If not a scheduling tool or failed → break inner, continue outer loop

### 5. Property ID System (Integer PK)
The `Property` model uses an **integer primary key** (seeded from JSON data, `autoincrement=False`). The `original_id` field mirrors it for backward compatibility. All tools now validate IDs early:
- `isdigit()` check → integer lookup → UUID fallback → title search (last resort)
- **Anti-hallucination**: If ID is non-numeric and non-UUID (e.g., `abc-123`, `prop-001`), returns immediate error telling LLM to use context IDs
- Few-shot examples use integer IDs like `1`, `2` (not `prop-001` as before)

### 6. Memory Architecture (Dual Store + Fallback)
- **Redis** (short-term): user context (state, selected_property_id, last_shown_properties, pending_scheduling_info), last 20 messages, intent cache (5 min TTL)
- **PostgreSQL** (long-term): user preferences, lead score, conversation history
- **In-memory fallback** (added Sprint 3): `_fallback_context` and `_fallback_messages` dicts preserve conversation context when Redis is down
- `selected_property_id` is saved after every `get_property_details`/`get_property_images` and injected into LLM context via `_build_messages()`
- `pending_scheduling_info` is saved by LLM and injected into context for context-aware scheduling
- Conversation context survives Redis restarts via the in-memory fallback

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

### 11. Render Blueprint — Redis Auto-Injection
When a Redis service is defined in `render.yaml` alongside a web service, Render **automatically injects** the `REDIS_URL` environment variable into the web service with the correct connection string (including auto-generated password). Do NOT manually set `REDIS_URL` if a Redis service is defined — the manual value overrides the auto-injected one and will have the wrong password.

## File Layout (Key Files)

```
inmueblebot/
├── app/
│   ├── main.py                          # FastAPI app, lifespan, CORS, routers, dashboard SPA
│   ├── agents/
│   │   ├── real_estate_agent.py          # Main agent: turn processing, tool loop (MAX=5)
│   │   ├── llm_router.py                 # Single OpenAI GPT-4o-mini provider
│   │   ├── tools.py                      # Tool implementations (~1001 lines, 13 tools)
│   │   ├── prompts.py                    # System prompt + few-shot examples (~600 lines, cleaned Sprint 3)
│   │   ├── gemini_client.py              # [DEPRECATED] Not used — kept for reference
│   │   ├── openrouter_client.py          # [DEPRECATED] Not used — kept for reference
│   │   └── llm.py                        # [DEPRECATED] MiniMax adapter — kept for reference
├── core/
│   ├── config.py                     # Pydantic-settings, multi-source .env loading
│   ├── state_machine.py              # Redis-backed FSM for conversation flow
│   ├── memory.py                     # Hybrid memory (Redis + PostgreSQL), ~695 lines
│   ├── classifier.py                 # OpenRouter-based intent classifier
│   ├── intent.py                     # Intent enum (7 intents)
│   ├── date_parser.py                # Spanish date/time parsing
│   ├── rate_limiter.py               # Redis-based token bucket (50 RPM global) — NEW May 10
│   ├── session.py                    # Session management
│   └── router.py                     # Simple router (legacy)
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

# Render API (infrastructure management)
curl -s -H "Authorization: Bearer \$RENDER_API_KEY" "https://api.render.com/v1/postgres" | jq .
curl -s -H "Authorization: Bearer \$RENDER_API_KEY" "https://api.render.com/v1/redis" | jq .

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
- **LLM**: `OPENAI_API_KEY` (single provider — GPT-4o-mini)
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
2. Fetch existing appointments from DB → inject into context
3. Check for handoff intent → early return
4. Build messages: system prompt + property/appointment context injection + conversation history
5. LLM call → tool execution → append results → loop (max 5 iterations, loop detection)
6. Loop detector: if same tool called twice AND success → break both loops with success response
7. Update state machine + lead score + preferences
8. Clean response text (remove debug/programming words, check for internal error patterns)
9. Return structured result
```

### Context Injection for Property References
The agent injects `<last_results>` XML tags with explicit mapping of option numbers to database IDs to prevent LLM hallucination of property IDs. The mapping format is:
```
<opci n 1> → ID=1 | Casa amplia | $180,000 | 4 hab | Posadas
```

### Context Injection for Appointments
When a user has existing appointments (`get_upcoming_appointments()` from DB), a system message is injected:
```
### CITAS EXISTENTES DEL USUARIO
{formatted appointment from format_appointment_confirmation()}
---
{formatted appointment}
```
With instruction: *"USA ESTOS DATOS EXACTOS si el usuario menciona cambiar o cancelar una cita. NO infieras ni adivines la hora desde la conversación. La base de datos es la ÚNICA fuente de verdad."*

### Context Injection for Pending Scheduling
When the LLM has pending scheduling info (from `pending_scheduling_info` in Redis), a system message is injected summarizing the pending property/date/time so the LLM doesn't re-ask.

### Appointment Confirmation
The `schedule_visit` tool embeds confirmed time in `<!--CONFIRMED:YYYY-MM-DD HH:MM-->` comment. **Times are formatted in `America/Argentina/Buenos_Aires` timezone** (converted from UTC stored in DB). The same pattern applies to `reschedule_appointment` and `cancel_appointment`.

### Rescheduling Flow (DB-First)
1. LLM calls `reschedule_appointment(appointment_id, new_date_str, new_time_str, phone)`
2. If `appointment_id` is not a valid UUID → auto-resolve from `phone` → user → latest appointment
3. Fetch current appointment data from DB (used as reference for missing params)
4. If no `new_date_str` → use existing appointment's date
5. If no `new_time_str` → use existing appointment's time
6. Contextual hour interpretation: if existing apt is PM and user says `7` → `19:00`, not `07:00`
7. Update DB + Google Calendar + return `format_appointment_confirmation()`

### Google Calendar Integration
The appointment service checks Google Calendar availability before creating appointments. On conflict, returns alternative time suggestions. 

**OAuth Setup**: `scripts/authenticate_calendar.py` — generates `credentials/token.json` via local browser flow.
**Production (Render)**: Token stored in Secret Files at `/etc/secrets/token.json` (read-only mount). Token refresh works in-memory but can't persist — expected behavior.
**Token refresh errors**: `invalid_grant` means token expired/revoked — regenerate locally and re-upload. `Errno 30` (read-only) means save-to-disk failed — safe to ignore, refresh still works for current session.
**Service resilience**: `_auth_failed` flag prevents repeated re-auth attempts on bad credentials. `reset()` clears the cache for manual re-initialization.

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
2. **No typing in agents** — `real_estate_agent.py` `_extract_rich_content` and many methods omit return types
3. **Hardcoded locations** — lists of cities/locations hardcoded across tools.py, memory.py, real_estate_agent.py
4. **Seed data loads every startup in development** — `lifespan` calls `seed_properties(force=True)` in dev mode, could reset manual edits

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
| `reschedule_appointment` | appointment_id, new_date_str, new_time_str, phone | Reschedule (auto-resolves if UUID invalid) |
| `cancel_appointment` | appointment_id, reason, phone | Cancel |
| `get_my_appointments` | phone | List appointments |
| `request_human_assistance` | phone, reason | Escalate to human |
| `refine_search` | refinement, previous_criteria | Narrow results |
| `get_property_images` | property_id | Get property images |
