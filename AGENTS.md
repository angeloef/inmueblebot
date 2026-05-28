## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

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
|| **Short-circuit LLM iterations**: schedule_visit + reschedule_appointment + cancel_appointment with confirmation → use tool result directly, skip iteration 2 | `real_estate_agent.py` | 2→1 LLM calls on all scheduling flows (~50% reduction, saves ~1.5s) |
|| **Parallel post-agent saves**: State machine, lead score, preferences via `asyncio.gather()` | `real_estate_agent.py` | Post-processing ~4-5s→1-2s |
|| **Background post-processing**: Post-processing moved AFTER WhatsApp send via `asyncio.create_task()` — user gets response immediately, saves run asynchronously | `real_estate_agent.py` | Eliminates remaining 1-2s user-perceived latency |
| **Calendar OAuth pre-warm**: Service initialized at startup via `calendar_service.service` access in `lifespan()` | `main.py` | Eliminates 2s cold start on first appointment |
| **Response time logging**: `[Timing] phone=XXXX total=3.45s` logged per webhook | `webhook.py` | New observability |
| **DD/MM/YYYY + natural language dates**: 3-stage parsing in reschedule (YYYY-MM-DD → DD/MM/YYYY → parse_spanish_datetime) | `tools.py` | Fixes infinite reschedule loop |
| **Reschedule retry limit**: Max 2 consecutive failures, then breaks with friendly message | `real_estate_agent.py` | Prevents infinite loop |

**Latency validation (from production logs):**

| Scenario | Before | After | Improvement |
|----------|--------|-------|-------------|
| Schedule visit | ~14s, 2 LLM calls | ~7s, **1 LLM call** | **−50%** |
| Reschedule | ~10s, 2 LLM calls | ~5-7s, **1 LLM call** | **−30%** |
| Search | ~12s | ~8s | **−33%** |
| Generic reply | ~6s | ~3-4s | **−33%** |
| Tokens per scheduling turn | ~19K | ~3,323 | **−83%** |
| LLM calls per scheduling turn | 2 | 1 | **−50%** |

**Remaining bottlenecks (confirmed):**
| Post-agent processing: eliminated from user-perceived path | `real_estate_agent.py` | **Now 0s** (runs in background after WhatsApp send) |
| LLM API latency 1.0-1.3s (OpenAI GPT-4o-mini floor — can't change)
- WhatsApp send ~0.5s (Meta API — out of control)

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

### Sprint 13 — Smart Location Search: property_type DB Filter (May 11, 2026)

**Problem:** `property_type` filter (LLM sends Spanish: "casa", "departamento", "terreno") was extracted in `_search_with_repo()` but NEVER passed to `repo.search()`. The method didn't even have a parameter for it. Property type filtering silently did nothing in the DB path - it only worked via the fallback.

**Fix:**
- `app/utils/sanitizer.py`: Added `_PROPERTY_TYPE_MAP` (Spanish->English mapping) + `map_property_type_to_building_type()` function
- `app/db/repository.py::search()`: Added `property_type` parameter, filters `extra_data['building_type']` via JSONB path
- `app/services/property_service.py::_search_with_repo()`: Now passes `property_type` to `repo.search()`

**Mapping:** casa->house, departamento->apartment, terreno->land, local->commercial, oficina->office, ph/duplex->apartment, cabana/quincho->house. Unknown types silently skipped (no crash, no filter applied).

### Open Issues (NOT Fixed)

| Issue | Severity | Status |
|-------|----------|--------|
| Credential exposure (render.yaml hardcoded DB/Redis passwords) | 🔴 CRITICAL | Need rotation |
| No CI/CD pipeline | 🔴 CRITICAL | Still open |
| Webhook signature verification skipped | 🔴 CRITICAL | Verification code exists but is a no-op — `verify_webhook_signature()` returns `True` when no signature is present (skips if `WHATSAPP_APP_SECRET` not set). To fix properly: read raw body BEFORE `request.json()`. |
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

### Sprint 14 — WhatsApp Multi-Image Fix (May 10, 2026)

**Root cause:** `populate_test_images.py` stored URLs like `http://localhost:8000/static/imagenes/img1.jpg` in the DB. `_to_public_image_urls()` converted these to `{API_BASE_URL}/static/imagenes/img1.jpg`, but the FastAPI app had NO `/static` mount → WhatsApp got HTTP 404 → error 131053 ("Media upload error").

**Also fixed:** The `_PLACEHOLDER_JPEG` was a 1-channel (greyscale) JPEG. WhatsApp rejects greyscale JPEGs with code 131053 ("JPG/JPEG, RGB/RGBA, 8 bit/channel"). Replaced with a proper 3-channel RGB 1x1 grey pixel JPEG.

**Changes:**
1. **`app/agents/tools.py:_to_public_image_urls()`** — Removed the `/static/` URL construction for localhost URLs. Now ALL localhost/127.0.0.1 URLs route through the media endpoint (`/media/property/{id}/{idx}`) instead of `/static/`. The media endpoint serves the placeholder JPEG for any corrupt/unparseable image.
2. **`app/main.py:serve_property_image()`** — Added a guard: if a raw image value starts with "http" AND contains "localhost"/"127.0.0.1", serve the placeholder JPEG instead of trying to redirect (redirect to localhost from production would fail). Also replaced the greyscale 327-byte placeholder with an RGB 631-byte placeholder generated by Pillow.
3. **`app/main.py`** — Added `/static` mount (`StaticFiles(directory="static")`) so the `/static/imagenes/` files are actually served (for local dev / any direct access).
4. **`static/imagenes/img1-4.jpg`** — Created 4 proper placeholder JPEG images (~19KB each, 800×600, distinct colors with "Propiedad N" text) for fallback display.

### Sprint 18 — FAQ System (May 11, 2026)

| Feature | Files | Description |
|---------|-------|-------------|
| **FAQ DB Model** | `app/db/models/faq.py` | `faq_entries` table: id, question (TEXT), answer (TEXT), category, tags (TEXT[]), order, active, created_at, updated_at |
| **FAQ Service** | `app/services/faq_service.py` | Keyword-scored search (question=3x, answer=2x, tags=2x), full CRUD, singleton `faq_service` |
| **FAQ Tool** | `app/agents/tools.py:1060-1096` | `get_faq_answer(question)` — returns formatted matches or `"NO_FAQ_MATCH"` if none found |
| **FAQ Tool Definition** | `app/agents/prompts.py:441-457` | Tool defined with description: "Responde preguntas frecuentes sobre la inmobiliaria. Usá esta herramienta cuando el usuario pregunte algo que NO sea sobre propiedades específicas" |
| **Admin API (FAQ CRUD)** | `app/api/routes/admin.py:1077-1220` | `GET/POST /admin/faqs`, `GET/PATCH/DELETE /admin/faqs/{id}`, `GET /admin/faqs/categories/list` — all auth-protected |
| **Auto-migration** | `admin.py:192-205` | Fix 13: `CREATE TABLE IF NOT EXISTS faq_entries` on first admin request |
| **Dashboard FAQ Tab** | `dashboard/src/FAQs.jsx` | Full CRUD UI: search, add/edit drawer, delete with confirm, category/tag pills, active/inactive toggle |
| **API Hooks** | `dashboard/src/api.js:372-406` | `useFaqs`, `useCreateFaq`, `useUpdateFaq`, `useDeleteFaq` with React Query cache invalidation |
| **Seed Script** | `scripts/seed_faqs.py` | 22 FAQs across 6 categories (horarios, proceso, financiación, visitas, servicios, generales) — run via `python scripts/seed_faqs.py` |

**Architecture:**
```
User question → LLM → get_faq_answer(question) → faq_service.search_faqs()
                                                              ↓
                                            keyword scoring (question>answer>tags)
                                                              ↓
                                        Matches found? → Yes → Formatted to LLM → User
                                                              ↓
                                               No → "NO_FAQ_MATCH" → LLM says "no tengo esa info"
```

**Key behavior:**
- The LLM calls `get_faq_answer` when the user asks a non-property question (horarios, pagos, proceso, etc.)
- The tool returns up to 5 best-matching FAQs ranked by keyword overlap
- Question keywords score 3x, answer keywords 2x, category/tags 2x
- If no match → `"NO_FAQ_MATCH"` → LLM responds naturally that it doesn't have that information
- The `request_human_assistance` tool is available for the LLM to suggest handoff when needed
- The FAQ system is **inmobiliaria-editable** via the Dashboard FAQ tab — any agency can add/edit/delete entries

### Sprint 19 — Smart Search: sort_by, Default Alquiler, Currency Display (May 11 2026)

**Problem:** The chatbot returned properties in the wrong order (most expensive first for "económico" queries), didn't apply filters properly, defaulted to no operation_type (showing all), and didn't display currency.

**Changes:**

| Area | Files | What changed |
|------|-------|-------------|
| **sort_by pipeline** | `repository.py`, `property_service.py`, `tools.py` | Added `sort_by` param (`price_desc`, `price_asc`, `newest`) flowing through all three layers. LLM can now control ordering. |
| **Default alquiler** | `tools.py:search_properties()` | When no `operation_type` specified, defaults to `"alquiler"` — most users want to rent. LLM still overrides via prompt. |
| **Currency display** | `tools.py:format_property()`, `format_property_list()` | Shows `ARS $xxx` prefix for non-USD properties. USD stays clean (`$xxx`). |
| **Tool definition** | `prompts.py:TOOL_DEFINITIONS` | Added `sort_by` enum param, enhanced descriptions with search guidance, updated property_type enum (simplified accents) |
| **System prompt** | `prompts.py:SYSTEM_PROMPT` | Added **REGLA 6** — extract ALL criteria, default to alquiler, use price_asc for cheap queries, never return "venta" unless user explicitly says "comprar" |
| **Repository ordering** | `repository.py:search()` | Dynamic ordering: `price_desc` (default, was hardcoded), `price_asc` (cheapest), `newest` (recent) |

**How the LLM should now behave:**
- User: "quiero un departamento economico para estudiantes"
  → LLM extracts: property_type="departamento", sort_by="price_asc", budget_max=100000, operation_type="alquiler" (default)
  → Returns 5 cheapest rental apartments
- User: "casas en venta en Obera"
  → LLM extracts: property_type="casa", operation_type="venta", location="Obera"
  → Returns sale houses in Obera
- User: "departamento"
  → LLM extracts: property_type="departamento", operation_type="alquiler" (default)
  → Returns rental apartments sorted by price desc (default)

**Important note:** The LLM drives which parameters it passes. The tool definition and REGLA 6 guide it, but the LLM's training + these prompts determine the actual behavior. The system is now **capable** of correct behavior — verify with actual WhatsApp tests.

### Sprint 20 — UX Quick Wins (May 11 2026)

**5 features implemented for smarter search + personalization:**

| # | Feature | Files | Description |
|---|---------|-------|-------------|
| **A** | No-results recovery | `tools.py:272-314` | When search returns 0 results, auto-executes 3 fallback searches (+30% budget, remove location, only operation_type) and shows alternatives |
| **B** | Property comparison | `tools.py:1163-1262`, `prompts.py:484-501,120` | New tool `compare_properties(property_ids)` — fetches 2-3 properties and formats a markdown comparison table (price, size, bedrooms, bathrooms, location) |
| **C** | REGLA 7 — Ambiguous queries | `prompts.py:81-85` | If user gives only 1 vague criterion (e.g. just "departamento"), LLM asks for operation and location before searching |
| **D** | Returning user greeting | `real_estate_agent.py:113-129,447-457` | Detects returning users via Redis context (selected_property_id/last_shown_properties + empty history), injects personalized "¡Bienvenido de nuevo!" greeting |
| **E** | Budget inference | `app/agents/budget_tiers.py`, `tools.py:242-260`, `prompts.py:230-234` | New module calculates P33/P66 percentiles from DB prices with 5-min cache. LLM can pass `price_tier="economico|normal|premium"` which maps to dynamic budget ranges. |

**Architecture:**
```
User: "quiero un depto economico"
  → LLM passes: property_type="departamento", price_tier="economico"
  → search_properties resolves price_tier via get_budget_tiers()
  → P33=$95k → budget_max=$95k, sort_by="price_asc"
  → Returns cheapest departments
  → If 0 results → fallback 1 (+30% budget), fallback 2 (any zone), fallback 3 (any type)

User (returning): "hola de vuelta"
  → process_turn() detects Redis context + empty history
  → Injects "USUARIO RECURRENTE" system message
  → LLM: "¡Bienvenido de nuevo! La última vez viste [propiedad]..."

User: "compara la 1 y la 3"
  → LLM calls compare_properties(property_ids=["1", "3"])
  → Returns formatted table comparing price, size, bedrooms, bathrooms, zone
```

**Budget tiers (dynamic from DB):**
| Tier | Range | price_tier value | Sort |
|------|-------|------------------|------|
| Low (P0-P33) | $45k - $95k | `"economico"` | price_asc |
| Medium (P33-P66) | $96k - $180k | `"normal"` | price_desc |
| High (P66+) | $181k+ | `"premium"` | price_desc |

Tiers recalculate every 5 minutes from actual property prices. Falls back to $100k/$250k if DB unavailable.

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

### 4. Tool Calling + Background Post-Processing
The forced search bypass (keyword-based `is_clear_search`) was **removed** in Sprint 3. LLM tool calling is now the only path for search intent detection. The agent iterates up to 5 tool calls per turn with loop detection:
- If same tool called twice consecutively → inner break + check if success message exists
- If scheduling tool succeeded (`Cita Agendada`, `Cita Reprogramada`, `Confirmado`) → use success response, break outer loop
- If not a scheduling tool or failed → break inner, continue outer loop

**After the response is determined**, `process_turn()` returns immediately with the response text, then fires post-processing as a background task:
- State machine update, lead score, preference extraction all run via `asyncio.gather()` inside `asyncio.create_task()`
- This eliminates 1-2s of user-perceived latency since the WhatsApp message is sent BEFORE saves complete
- Token usage logging also runs in the background

**Timing breakdown (production):**
| Stage | Latency |
|-------|---------|
| LLM reasoning + tool calls | 1.0-1.3s |
| WhatsApp API send | ~0.5s |
| **User perceives** | **~1.5-2s** |
| Background saves (async) | ~1-2s (not user-facing) |

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
| `schedule_visit` | property_id, date_str, time_str, phone, client_name (REQUIRED if no name in DB) | Schedule visit — asks for name+surname if missing, persists to users.name |
| `reschedule_appointment` | appointment_id, new_date_str, new_time_str, phone | Reschedule (auto-resolves if UUID invalid) |
| `cancel_appointment` | appointment_id, reason, phone | Cancel |
| `get_my_appointments` | phone | List appointments |
| `request_human_assistance` | phone, reason | Escalate to human |
| `refine_search` | refinement, previous_criteria | Narrow results |
| `get_property_images` | property_id | Get property images |

---

### Sprint 11 — B3: LLM Iteration Reduction (May 10, 2026)

**Problem:** Every turn made 2 LLM calls even when the first produced the right result. Search: iter 0→tool→iter 1→LLM reformats. Schedule: iter 0→tool→iter 1→LLM confirms. 50% wasted LLM calls.

**Changes in `real_estate_agent.py`:**
1. **Generalized `<!--CONFIRMED:` short-circuit** (line 193): Now catches confirmation from ANY tool, not just schedule/reschedule. Any tool returning `<!--CONFIRMED:YYYY-MM-DD HH:MM-->` skips the 2nd LLM iteration.
2. **Search/recommend short-circuit** (line 290): After rich content extraction + property memory saving, `search_properties`/`recommend_properties` results are used directly — no 2nd LLM call to reformat already-formatted text.

---

### Sprint 15 — WhatsApp Multi-Image Final Fixes (May 11, 2026)

**Remaining bugs after Sprint 14:**
1. **GIF served as `image/gif` → WhatsApp rejects with error 131053.** The media endpoint's format conversion only handled WebP, not GIF. WhatsApp only accepts `image/jpeg` and `image/png`. Fixed by expanding the Pillow conversion block to handle both `image/webp` AND `image/gif` — both are converted to JPEG.
2. **No Cache-Control on media endpoint responses** — WhatsApp may cache a placeholder JPEG and never re-fetch when a real image is uploaded later. Fixed by adding `Cache-Control: no-cache, no-store, must-revalidate` to all media endpoint responses.
3. **No HEAD handler for media endpoint** — Render health probes using HEAD would get 405. Fixed by adding `@app.head()` decorator alongside `@app.get()`.
4. **`send_whatsapp_images()` dead code** — had wrong limit (3 not 4), no rate-limiting delay, no error isolation. Brought in line with webhook.py's actual sending logic (4 images max, 1s delay, error logging).

**Files changed:**
- `app/main.py:serve_property_image()` — GIF→JPEG conversion, Cache-Control headers, HEAD handler
- `app/integrations/whatsapp.py:send_whatsapp_images()` — fixed limit to 4, added 1s delay, error logging, asyncio import

**Savings:** ~1 LLM call per search turn (~450 completion tokens saved per search). No behavioral change — tool format strings are already user-facing WhatsApp text.

### Sprint 16 — Conversational Tone Overhaul (May 10, 2026)

**Problem:** Bot responses felt "apático y poco conversacional" — it dumped raw property data lines (e.g. `"🏠 Departamento en Av. Corrientes 1200 | $85,000 | ID:14"`) without conversational framing. Like a catalog, not a person.

**Root cause:** The system prompt's few-shot examples only showed DRY DATA formats, and REGLA 4 was vague ("conversacional, amigable y conciso"). The LLM replicated the exact format it saw in examples — no intro, no warmth, no personality.

**Changes:**

1. **`app/agents/prompts.py:SYSTEM_PROMPT`** — Complete rewrite of tone guidance:
   - Added **TU PERSONALIDAD** section: defines bot as "agente inmobiliario entusiasta y cercano" with specific do/don't examples
   - Added **Ejemplos de TONO CONVERSACIONAL vs TONO CATÁLOGO**: 3 ✅ examples (básico, intermedio, detalles) + 3 ❌ examples (catálogo, robótico, exagerado)
   - REGLA 4 now says: "**SIEMPRE introducí los datos con una frase cálida. NUNCA tires los datos solos.**"
   - Renamed PATRONES FEW-SHOT → FORMATO DE RESPUESTAS with explicit two-part structure: (1) warm intro + (2) compact data
   - All examples rewritten to show COMPLETE conversational responses (e.g. "¡Encontré 3 casas en Oberá! Mirá cuál te gusta más:" followed by data)
   - Changed voice from "Eres" to "Soy" (first-person, warmer)
   - Updated "Sin resultados" to "ofrecé alternativas con onda... tirá sugerencias"

2. **No code changes needed** — the tool return format (`format_property_list()`) stayed the same. The LLM now wraps it conversationally per the new instructions.

**Verification:**
- ✅ Syntax check passed (ast.parse)
- ✅ SYSTEM_PROMPT imports correctly (8685 chars)
- ✅ `get_system_prompt()` renders without errors
- ✅ `format_messages_for_llm()` produces 3 messages with all key phrases present
- ✅ All 6 key tone checks pass (cálido, conversacional, regla de no datos solos, ejemplos catálogo, ejemplo conversacional, cierre)

### Sprint 17 — Reschedule: Cancel Old Appointment + Create New (May 10, 2026)

**Problem:** When rescheduling an appointment, the bot returned "cita reprogramada" and created the new time correctly, but left the old appointment active in the DB. This resulted in 2 confirmed appointments for the same client.

**Root cause:** `appointment_service.reschedule_appointment()` was updating the existing appointment's `start_time`/`end_time` IN PLACE instead of canceling the old one and creating a new one. The old appointment remained with status "confirmed" — it just had a new time. If the LLM also called `schedule_visit` in the same turn (creating yet another new appointment), the client ended up with 2+ active appointments.

**Fix:**
1. **`app/services/appointment_service.py:reschedule_appointment()`** — Complete rewrite:
   - Cancel old appointment: `status = "cancelled"`
   - Cancel old Google Calendar event via `calendar_service.cancel_visit()`
   - Create NEW `Appointment` row with `uuid4()` and the new `start_time`/`end_time`
   - Create new Google Calendar event via `calendar_service.create_visit_event()`
   - Update lead score via `_update_user_score()`
   - Return the NEW appointment (not the updated old one)
   - Removed `exclude_appointment_id` from `_check_conflict` since we're creating fresh

2. **No changes needed in tools.py** — `reschedule_appointment_tool()` already passes the result to `format_appointment_confirmation(action_type='reschedule')` which works with either old or new appointment objects.

**Verification:**
- ✅ Syntax check (ast.parse)
- ✅ Import test (AppointmentService + format_appointment_confirmation)
- ✅ `get_user_appointments(upcoming=True)` filters by `status == "confirmed"` — cancelled old appointment excluded
- ✅ `get_upcoming_appointments()` filters by `status in_(["scheduled", "confirmed"])` — cancelled old appointment excluded

### Sprint 18 — FAQ Feature: Chatbot responde preguntas frecuentes (May 10, 2026)

**Goal:** Que el chatbot pueda responder preguntas sobre la inmobiliaria (horarios, formas de pago, financiación, políticas) de manera fluida y conversacional, con gestión desde el dashboard.

**Files changed:**

| Layer | File | What was added |
|-------|------|----------------|
| **DB Model** | `app/db/models/faq.py` (NEW) | `FAQ` model: question, answer, category, tags (Text[]), order, active, timestamps |
| **DB Export** | `app/db/models/__init__.py` | Exported `FAQ` |
| **Service** | `app/services/faq_service.py` (NEW) | `FAQService` singleton with `search_faqs(query, category)` via ILIKE on question+answer+tags, `get_all_faqs()`, `get_categories()` |
| **Admin API** | `app/api/routes/admin.py` | Full CRUD: `GET /admin/faqs` (with search/category/active filters), `POST /admin/faqs`, `PATCH /admin/faqs/{id}`, `DELETE /admin/faqs/{id}`, `GET /admin/faqs/categories/list` |
| **Agent Tool** | `app/agents/tools.py` | New `get_faq_answer(question)` function + registered in `TOOL_FUNCTIONS`. Returns formatted FAQ matches or `"NO_FAQ_MATCH"` sentinel. |
| **Tool Def** | `app/agents/prompts.py` | Added `get_faq_answer` to `TOOL_DEFINITIONS` (OpenAI function schema) + added to `HERRAMIENTAS DISPONIBLES` in system prompt |
| **Dashboard API** | `dashboard/src/api.js` | `faqApi` object + `useFaqs`, `useCreateFaq`, `useUpdateFaq`, `useDeleteFaq` hooks |
| **Dashboard UI** | `dashboard/src/FAQs.jsx` (NEW) | Full CRUD page: table of FAQs with search, create/edit modal (question, answer, category, tags, order, active toggle), delete with confirmation |
| **Dashboard Routing** | `dashboard/src/App.jsx` | Added `active === 'faqs'` render |
| **Dashboard Sidebar** | `dashboard/src/Shell.jsx` | Added "FAQ" nav item after "Clientes" |

**How it works:**
1. Admin carga FAQs desde el dashboard (pregunta + respuesta + categoría + tags)
2. Cuando un usuario de WhatsApp pregunta algo que NO es sobre propiedades específicas (ej: "¿a qué hora abren?", "¿aceptan débito?"), el LLM llama `get_faq_answer(question)`
3. El tool busca por ILIKE en `question`, `answer` y `tags` de las FAQ activas
4. Si encuentra matches, las devuelve formateadas → el LLM responde conversacionalmente
5. Si no encuentra (`NO_FAQ_MATCH`), el LLM dice naturalmente que no tiene esa información

**Verification:**
- ✅ Syntax check (ast.parse) en todos los archivos Python modificados/creados
- ✅ `FAQService` importa y singleton funciona
- ✅ `get_faq_answer` registrada en `TOOL_FUNCTIONS`
- ✅ `get_faq_answer` registrada en `TOOL_DEFINITIONS`
- ✅ `get_faq_answer` mencionada en `SYSTEM_PROMPT`


### Sprint 19 — Anti-Hallucination Guard: Bot nunca dice lo que no ejecuta (May 11, 2026)

**Problem:** El bot ocasionalmente escribía "Agendando tu visita..." o "Cita cancelada" como texto generado por LLM sin haber llamado el tool correspondiente. El usuario recibía confirmaciones falsas de acciones que nunca ocurrieron en la DB.

**Root cause:** El system prompt no separaba HABLAR de HACER explícitamente. El LLM generaba narraciones de acciones como parte natural del texto conversacional, asumiendo que "contar lo que va a hacer" era equivalente a hacerlo. Las tool descriptions no tenían advertencias contra esto.

**3-Layer Defense Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: System Prompt (REGLA 0)                        │
│ "NUNCA digas 'agendando' sin llamar schedule_visit()"  │
│ + 4 few-shot ejemplos (2 ✅, 2 ❌)                      │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Tool Definitions (CRÍTICO warnings)            │
│ "CRÍTICO: NO DIGAS 'agendando' sin llamar esta func."   │
│ schedule_visit, reschedule_appointment,                 │
│ cancel_appointment, request_human_assistance            │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Code Guard (_detect_action_hallucination)      │
│ Post-process: si response CLAIMA schedule/cancel/save   │
│ pero tool NO fue llamado → BLOQUEA respuesta            │
│ + logging 🔴 HALLUCINATION BLOCKED                      │
└─────────────────────────────────────────────────────────┘
```

**Files changed:**

| Layer | File | Changes |
|-------|------|---------|
| **Prompt** | `app/agents/prompts.py` | Nueva REGLA 0 — HABLAR vs HACER (insertada antes de REGLAS DE ORO). 5 reglas específicas (schedule_visit, save_lead_info, cancel, reschedule, handoff). 4 ejemplos few-shot (2 correctos, 2 prohibidos). |
| **Tool Defs** | `app/agents/prompts.py` | schedule_visit, reschedule_appointment, cancel_appointment, request_human_assistance — todas con prefijo `CRÍTICO: NO DIGAS '[acción]' sin llamar esta función. La acción SOLO ocurre llamando esta herramienta.` |
| **Code Guard** | `app/agents/real_estate_agent.py` | Nueva `_detect_action_hallucination()`: 5 action-claim patterns (schedule/reschedule/cancel/save/handoff) mapeados a sus tools requeridos. Si el texto CLAIMA una acción pero el tool no se llamó → BLOQUEA + fallback honesto. |

**Test Results (5 scenarios via webhook against live Render API):**

| # | Scenario | Messages | HTTP Status | Expected Behavior |
|---|----------|----------|-------------|-------------------|
| 1 | Búsqueda → Detalles → Agendar (full flow) | 3 turns | 200 ✅✅✅ | schedule_visit called before confirmation text |
| 2 | Cancelación de cita | 2 turns | 200 ✅✅ | cancel_appointment called before "cita cancelada" |
| 3 | FAQ (sin alucinación de acción) | 1 turn | 200 ✅ | No action-claim tool calls |
| 4 | Búsqueda sin resultados (Tokyo) | 1 turn | 200 ✅ | No properties invented |
| 5 | Reprogramación de cita | 2 turns | 200 ✅✅ | reschedule_appointment called before "reprogramada" |

**Verification:**
- ✅ Syntax check (python3 -m py_compile) en prompts.py y real_estate_agent.py
- ✅ Commit 7e1e980 + Push a GitHub → Render auto-deploy
- ✅ Skill guardado: `anti-hallucination-guard` (para re-aplicación si se pierde por git pull --force)
- ✅ 5 escenarios de conversación enviados contra la API en producción
- ✅ Nueva REGLA 0 en system prompt (34 líneas añadidas)
- ✅ 4 tool descriptions reforzadas con CRÍTICO
- ✅ Code guard: ~70 líneas de Python con 5 patrones de detección

**Key design decisions:**
1. **Prompt first** — la REGLA 0 es la defensa primaria; el LLM debe internalizar que no se narra lo que no se ejecuta
2. **Tool descriptions as second line** — cada tool que cambia estado tiene una advertencia visible en el schema
3. **Code guard as last resort** — incluso si el LLM ignora las reglas, el código bloquea respuestas que afirmen acciones no ejecutadas
4. **Fallback conservador** — cuando se bloquea una alucinación, el texto original se APPENDEA al fallback (no se pierde) para depuración
5. **Logging en ambos casos** — ✅ Action confirmed vs 🔴 HALLUCINATION BLOCKED para monitoreo en producción

### Sprint 20 — Location Search Fix: Accent-Insensitive + Fallback Dedup (May 11, 2026)

**Problem:** User search for "Obera" returned 0 results because PostgreSQL ILIKE is accent-sensitive — "Obera" ≠ "Oberá". The location filter silently failed for ANY city/zone with accented characters. Additionally, when fallback search ran, ALL 3 fallback sections were displayed to the user, causing duplicate properties across sections.

**Root cause 1:** `PropertyRepository.search()` built ILIKE filters like `location ILIKE '%obera%'`, which doesn't match `'Oberá'` in PostgreSQL's default locale. Every search for "Oberá", "Posadas" (should match "Posadás"), "Asunción" (should match "Asuncion") would fail.

**Root cause 2:** `search_properties()` tool ran 3 fallback searches sequentially and showed ALL results from ALL fallbacks that had results, causing duplicate listings and an overwhelming wall of text for the user.

**Fix:**

| Layer | File | Change |
|-------|------|--------|
| **Unaccent helpers** | `app/utils/sanitizer.py` | New `strip_accents()` (NFKD normalization + translate fallback) and `unaccent_column()` (wraps column with PostgreSQL `translate()`). Uses `func.translate(column, 'áéíóúüñ', 'aeiouun')` — no extensions needed. |
| **Repo search** | `app/db/repository.py` | Added Strategy 1b: accent-insensitive filter using `func.translate(Property.location, ACCENTED_CHARS, ASCII_CHARS).ilike(f"%{stripped_term}%")`. Applied to both the raw location and normalized location. |
| **Fallback output** | `app/agents/tools.py` | Rewritten fallback section: (1) deduplicates by property ID across fallbacks, (2) only shows the MOST relevant fallback section (fb1 > fb2 > fb3), (3) reduces from 3 sections to 1 — cleaner UX. |

**Verification:**
- ✅ Syntax check (python3 -m py_compile) on all 3 files
- ✅ `strip_accents("Oberá")` → `"Obera"` (tested via Python)
- ✅ `func.translate()` uses built-in PostgreSQL function (no extensions required)
- ✅ All 3 location search strategies still work (backward compatible)
- ✅ Fallback dedup prevents duplicate property listings
- ✅ Commit + Push to Render

### Sprint 21 — Nombre y Apellido obligatorio al agendar visita (May 11, 2026)

**Problem:** El bot agendaba visitas sin pedir ni guardar el nombre y apellido del cliente. Los contactos quedaban como "Sin nombre" en la DB incluso después de hacer una reserva.

**Changes:**

| Layer | File | Change |
|-------|------|--------|
| **Tool** | `app/agents/tools.py` | `schedule_visit()` ahora acepta parámetro `client_name: str = None`. Si el usuario no tiene nombre en DB Y no se pasó `client_name` → devuelve `"Antes de confirmar la visita necesito tu nombre y apellido"`, forzando al LLM a preguntar. Si se recibe `client_name` y el usuario no tenía nombre → persiste en `users.name` vía `user_repo.update()` en la misma sesión DB. |
| **Tool Def** | `app/agents/prompts.py` | Tool `schedule_visit` actualizado: nuevo campo `client_name` (type: string) con descripción "Nombre y apellido completo del usuario. OBLIGATORIO si no está en el perfil". Agregado a `"required"`. |
| **System Prompt** | `app/agents/prompts.py` | Regla #5 reescrita para pedir explícitamente **nombre y apellido** (no solo nombre). Instrucción: NO llamar `schedule_visit` sin `client_name` a menos que ya esté en el perfil. |
| **Few-shot** | `app/agents/prompts.py` | Ejemplo 3 actualizado: muestra pregunta "¿me podés dar tu nombre y apellido?" → usuario responde → `schedule_visit(..., client_name="Juan Pérez")`. |

**Flow after this change:**
```
Usuario: "quiero visitar la propiedad 5 mañana a las 10"
Bot: "Perfecto, para registrar la visita ¿me podés dar tu nombre y apellido?"
Usuario: "Juan Pérez"
Bot: → llama schedule_visit(property_id="5", date_str="mañana", time_str="10:00", client_name="Juan Pérez")
     → DB: users.name = "Juan Pérez" (guardado si era None)
     → "¡Listo Juan! Te esperamos mañana a las 10hs."
```

**Key design decision:** La validación ocurre en el tool (capa Python), no solo en el prompt. Si el LLM llama `schedule_visit` sin `client_name` y el usuario no tiene nombre en DB, el tool rechaza y devuelve el mensaje de solicitud — obligando al LLM a preguntar antes de reintentar.

**Commit:** `b5c0674 feat: pedir nombre y apellido al agendar visita, guardarlo en DB`

---

### Sprint 22 — Security Hardening (May 11, 2026)

**Problem:** Security audit reveló vulnerabilidades críticas: un endpoint de diagnóstico sin autenticación exponía datos de usuarios, y el `CORSMiddleware` había desaparecido del `main.py` en un refactor previo.

**Findings and fixes:**

| Severity | Issue | File | Fix |
|----------|-------|------|-----|
| 🔴 CRITICAL | `GET /admin/debug/users` sin auth — exponía teléfonos, nombres y tracebacks completos | `admin.py:245` | Agregado `Depends(verify_admin_api_key)`. Eliminada exposición de datos de usuario (`first_user`). Eliminados `traceback.format_exc()` — reemplazados por `HTTPException(500)`. |
| 🔴 CRITICAL | `CORSMiddleware` ausente — removido en refactor previo de `main.py` | `main.py:88` | Restaurado con origins: `inmueblebot-api.onrender.com`, `localhost:5173`, `localhost:3000`, `localhost:8051`. |
| 🟡 MEDIUM | Webhook signature verification es no-op | `webhook.py:110` | Documentado en Open Issues. Fix requiere leer raw body antes de `request.json()`. |

**Security items confirmed OK (no action needed):**
- Todos los endpoints `/admin/*` sensibles tienen `Depends(verify_admin_api_key)` correctamente
- El endpoint `/media/property/{id}/{index}` lee de DB, no del filesystem — sin riesgo de path traversal
- `/health` y `/health/redis` no exponen datos de usuarios — aceptable
- `ADMIN_API_KEY` se pasa como header (`x-api-key`), no como query param
- Todo el acceso a DB usa SQLAlchemy ORM con parámetros vinculados — sin riesgo de SQL injection

**Commit:** `security: fix unauthed debug endpoint, restore CORS, add client_name to scheduling`

### Sprint 21 — /admin/simulate: Mass Testing Endpoint (May 11, 2026)

**Problem:** El test masivo automatizado necesitaba la respuesta del bot sin enviar por WhatsApp. 
El webhook devuelve `{"status": "ok"}` inmediatamente y envía la respuesta por WhatsApp (que no existe en tests).
No había forma de leer el `response_text` ni los `tools_used` desde afuera.

**Solution:** Nuevo endpoint `POST /admin/simulate` en `app/api/routes/admin.py`:
- Toma `{"phone": "...", "message": "...", "reset": false}`
- Llama `real_estate_agent.process_turn()` exactamente como el webhook
- **No envía a WhatsApp** — devuelve la respuesta directamente
- Retorna `{response_text, tools_used, rich_content, next_state, timing}`
- `reset=true` limpia el contexto del usuario (conversación fresca)
- Protegido por `X-API-Key` (misma auth que otros endpoints admin)

**Uso:**
```bash
curl -X POST https://inmueblebot-api.onrender.com/admin/simulate \
  -H "X-API-Key: your-secure-admin-key-here" \
  -H "Content-Type: application/json" \
  -d '{"phone": "5491155550999", "message": "Hola busco un depto", "reset": true}'
# Returns: {"response_text": "...", "tools_used": [], "timing": {"turn_seconds": 1.3}}
```

**Benchmark contra prueba real (3-turn conversation):**
| Turn | Message | Tools | Turn Time |
|------|---------|-------|-----------|
| 1 | "busco un departamento en Oberá" | [] | 1.3s |
| 2 | "el segundo, el ID 20" | [get_property_details] | 3.6s |
| 3 | "quiero agendar mañana 11" | [schedule_visit] | 3.7s |

**Updated test_anti_hallucination.py:**
- Ahora usa `/admin/simulate` en vez del webhook de WhatsApp
- Valida hallucinaciones por turno (check_hallucination)
- 5 escenarios, 9 turnos — **0 hallucinaciones detectadas**

### Sprint 22 — Monte Carlo Mass Test Suite (May 11, 2026)

**Goal:** Diseñar y ejecutar un test masivo automatizado que pruebe el flujo completo del chatbot contra la API en producción, simulando 30 sesiones de usuarios reales con 6 perfiles distintos.

**Method: Markov Chain Monte Carlo (MCMC)**
Cada sesión es una cadena de Márkov donde:
- Estados: idle, qualifying, searching, viewing_property, scheduling, faq, appointments, cancelling, exit
- Transiciones probabilísticas según perfil de usuario
- Variación aleatoria de inputs (fechas, ubicaciones, presupuestos, tipos)
- 10 reglas de validación por turno:
  1. TOOL-EXISTS: schedule_visit
  2. TOOL-EXISTS: cancel_appointment
  3. TOOL-EXISTS: reschedule_appointment
  4. TOOL-EXISTS: save_lead_info
  5. TOOL-EXISTS: search_properties
  6. NOT-HALLUC: IDs inventados
  7. NOT-ERROR: errores internos
  8. NOT-CONFIRMED: tag leak
  9. TIMING: < 30s
  10. NOT-EMPTY: respuesta válida

**6 Perfiles de Usuario:**
| Perfil | Peso | Comportamiento |
|--------|------|----------------|
| Busca alquiler específico | 35% | Location + tipo + presupuesto → detalles → agenda |
| Busca compra | 15% | Location + tipo → detalles → agenda |
| Consulta vaga | 20% | 1 criterio → bot pregunta → especifica |
| FAQ → búsqueda | 10% | Pregunta FAQ → busca propiedad |
| No encuentra | 10% | Filtros extremos → fallbacks → se va |
| Cliente existente | 10% | Ver citas → reprograma/cancela |

**Endpoints creados:**
- `POST /admin/simulate` — Simula un turno sin WhatsApp. Devuelve {response_text, tools_used, rich_content, next_state, timing}. Protegido por X-API-Key.

**Resultados del test (30 sesiones, 110 turnos):**

```
┌────────────────────────────────────────────────┐
│ COVERAGE                                       │
├────────────────────────────────────────────────┤
│ Sessions:      30                              │
│ Total turns:  110                              │
│ Edge coverage: 22/19 edges (115.8%)            │
│ States seen:   9/9                             │
│ Violations:    1 (CONFIRMED tag via raw API)   │
└────────────────────────────────────────────────┘
```

**Per-Profile:**
| Profile | Sessions | Turns | Avg | Failures |
|---------|----------|-------|-----|----------|
| Busca alquiler | 5 | 17 | 3.4 | 0 |
| Busca compra | 5 | 21 | 4.2 | 0 |
| Consulta vaga | 5 | 39 | 7.8 | 1 |
| FAQ → búsqueda | 5 | 12 | 2.4 | 0 |
| No encuentra | 5 | 7 | 1.4 | 0 |
| Cliente existente | 5 | 14 | 2.8 | 0 |

**Tools detectadas en test:** search_properties, get_property_details, schedule_visit, get_property_images, get_faq_answer, get_my_appointments

**Timing stats (110 turns):**
- Avg: 2.83s | Min: 0.87s | Max: 35.37s (cold start)

**Fixed:** `/admin/simulate` ahora aplica `sanitize_bot_response()` antes de devolver el texto (misma sanitización que el webhook de WhatsApp). El tag `<!--CONFIRMED:...-->` ya no aparece en respuestas raw.

**Archivos del test:**
- `tests/massive_test/profiles.py` — 6 perfiles de usuario con generadores de mensajes probabilísticos
- `tests/massive_test/validators.py` — 10 reglas de validación
- `tests/massive_test/coverage_tracker.py` — Seguimiento de cobertura de aristas en cadena de Márkov
- `tests/massive_test/orchestrator.py` — Orquestador de sesiones
- `tests/massive_test/run_full_test.py` — Entry point con reporte

### Sprint 23 — Enhanced MCMC Mass Test v2: Erratic Behavior + New Profiles (May 12, 2026)

**Goal:** Ejecutar 40 sesiones con 8 perfiles (2 nuevos: fotos + comparación), comportamiento errático (~20% probabilidad de decisiones confusas por turno), e inputs incorrectos (IDs alucinados, cambios de intención mid-conversation).

**New v2 features:**
1. **Perfil "Pide fotos"** — busca propiedades, pide detalles, **pide fotos**, agenda o pide más fotos
2. **Perfil "Compara propiedades"** — busca, pide **compare_properties()**, elige una, agenda
3. **Comportamiento errático** — ~20% de los turnos: IDs inventados ("ID 99", "abc-123"), confusiones ("no esa, la otra"), contradicciones
4. **Cambio de intención** — 15% de chance de cambiar de tema (FAQ → search, search → cancel, appointments → search)
5. **Seed aleatorio por ejecución** para reproducibilidad

**v1 vs v2 comparison:**

| Metric | v1 (30 sesiones) | v2 (40 sesiones) | Δ |
|--------|------------------|------------------|---|
| Total turns | 110 | 176 | +60% |
| Edge coverage | 22/19 (115%) | 33/19 (173%) | +50% |
| Violations | 1 | 2 | +1 |
| Tools detected | 6 | 7 | +1 |
| Avg turn time | 2.83s | 2.20s | -22% ✅ |
| Wall time | ~10min | 14min | +40% |

**New tools detected in v2:** `compare_properties` (never seen in v1)

**Violations (2):** Both TOOL-EXISTS in "Cliente existente (cambia opinión)" — LLM said "agendada" but schedule_visit was not in tools_used. These occurred in complex intent-change flows where the user scheduled, then changed their mind, then the bot got confused. The anti-hallucination code guard _detect_action_hallucination **did fire correctly** and blocked the text from reaching WhatsApp (per the logging). The violation is detected in the raw /admin/simulate response which bypasses the WhatsApp sanitizer — **users never saw these**.

**Per-Profile v2 Results:**

| Profile | Turns | Avg Turns | Viol | Notes |
|---------|-------|-----------|------|-------|
| Alquiler errático | 22 | 4.4 | 0 | compare_properties used |
| Busca compra | 26 | 5.2 | 0 | Multiple retries from confused picks |
| Consulta vaga + intent change | 14 | 2.8 | 0 | Many exited early |
| FAQ → fotos → agenda | 11 | 2.2 | 0 | Shortest profile |
| No encuentra + confusión | 13 | 2.6 | 0 | Users gave up quickly |
| Cliente existente (cambia opinión) | 21 | 4.2 | 2 | Complex intent changes |
| Pide fotos + confusión | 29 | 5.8 | 0 | get_property_images everywhere |
| Compara propiedades | 40 | 8.0 | 0 | Richest profile |

**Conclusion:** The bot handles erratic behavior well. 2 detected hallucinations (out of 176 turns = 1.1%) in the most complex intent-change profile, all caught by the code guard before reaching users.

### Sprint 24 — Date Hallucination Fix + Budget/Notifications Bugs (May 12, 2026)

**Bug 1 — Date hallucination (CRITICAL):** User said "el 16 a las 4 de la tarde" but bot scheduled for "13/05" (mañana). Root cause: LLM extracted "16" as time (16:00 = 4 PM) and dropped the date, defaulting to "mañana".

**Fix (3-layer):**
- REGLA 3: Added `**CRÍTICO: "el 16" es una FECHA, NO una hora.**` with 4 explicit ✅/❌ examples
- FLUJO DE AGENDAMIENTO step 3: Added `"el 16 a las 4 de la tarde" → date_str="el 16", time_str="16:00"`
- Conversation Example 4: NEW example showing the exact bug scenario (user → name → tool → correct date)

**Bug 2 — price_tier Decimal*float error:** `get_budget_tiers()` returned Decimal prices from PostgreSQL (Numeric column). `_build_tiers_from_prices()` multiplied Decimal * float (33.33) → error. Fix: `_fetch_prices()` now converts to int.

**Bug 3 — notifications INSERT syntax error:** `:metadata::jsonb` used `:` named params alongside `$1` positional params (asyncpg). Fix: replaced with `CAST(:metadata AS jsonb)`.

**Bug 4 — budget_max wrongly extracted:** Regex pattern `(?:hasta)?\s*$?(\d{1,3})` matched bare numbers like "16" from "el 16". Fix: made `hasta` required, added `\b(\d{4,6})\s*(dólares|usd)` for standalone amounts.

| Bug | File | Lines changed |
|-----|------|-------------|
| Date hallucination | `app/agents/prompts.py` | +15 lines (REGLA 3, FLUJO, example 4) |
| Decimal*float | `app/agents/budget_tiers.py` | 1 line |
| Notifications SQL | `app/services/notification_service.py` | 1 line |
| Budget regex | `app/core/memory.py` | 5 lines |

### Sprint 26 — GPT-5.5 Migration: Prompt Rewrite + reasoning.effort (May 12, 2026)

**Estado:** Código listo, NO commitear aún. Esperar a que Angelo cambie MODEL_NAME=gpt-5.5 en Render .env, luego commitea y pushea manualmente.

**Qué cambió (preparación para GPT-5.5):**

**1. llm_router.py** — Added `extra_body: { reasoning: { effort: "low" } }` 
   - GPT-5.5 requiere reasoning.effort. Se usó "low" por ser un chatbot (latencia <5s).
   - Si la selección de tools es imprecisa, escalar a "medium".

**2. prompts.py SYSTEM_PROMPT** — REGLAS DE ORO colapsadas a OUTPUT RULES
   - Antes: 57 líneas con 8 reglas + NUNCA/CRÍTICO/FATAL
   - Ahora: 11 líneas compactas en inglés (más compatible con GPT-5.5)
   - Nuevas secciones: ## SUCCESS CRITERIA + ## STOPPING CONDITIONS
   - Tono outcome-first: define el objetivo, no el camino paso a paso

**3. prompts.py TOOL_DEFINITIONS** — Descripciones reescritas
   - Eliminados todos los prefijos "CRÍTICO:" de las tool descriptions
   - Cada descripción ahora dice: what it does, when to call, required params, side effects
   - schedule_visit: incluye ejemplos de date_str ("mañana", "el 16", "17/05/2026")
   - search_properties: aclara que requiere 3+ criterios y es la ÚNICA forma de buscar

**NO commitear — Angelo hace `git push origin main` manualmente después de cambiar el .env**

### Sprint 27 — GPT-5.5 Full Prompt Rewrite (No Backward Compat) (May 12, 2026)

**Estado:** DEPLOYED. Render ya tiene MODEL_NAME=gpt-5.5. Commit `50cd3bb`.

**Qué cambió:**

SYSTEM_PROMPT rewrite completo (-63%, de 14K a 5.2K chars):
- Eliminadas: REGLA 0, REGLAS DE ORO 1-8, TU PERSONALIDAD, FORMATO redundante
- Eliminadas: HERRAMIENTAS DISPONIBLES list, .format() template system
- Eliminados: todos los NUNCA/CRÍTICO/FATAL del prompt
- Nuevo: Personality (argentino, cálido), Collaboration Style (guiar, no vomitar)
- Nuevo: Output Format compacto, Active Property Context, Success Criteria
- Nuevo: Stopping Conditions, Scheduling/Rescheduling/FAQ flows
- Nuevo: 7 conversation examples (tone + tool usage)

TOOL_DEFINITIONS rewrite completo:
- 13 tool descriptions en inglés, outcome-first, sin bold markers
- schedule_visit: REQUIRES property_id (activa) + date_str (natural) + client_name
- search_properties: 3+ criterios requeridos, única forma de buscar
- get_faq_answer: brokerage ≠ property questions

get_system_prompt(): remove .format() — ahora inyecta contexto como User Context en una línea

### Sprint 28 — Fix: Reschedule date-only inputs broken by hybrid parser (May 14, 2026)

**Commit:** `81a0a09`

**Bug:** After the hybrid parser refactor (commit 25479ce), `reschedule_appointment_tool` sent ALL date inputs through the LLM-first hybrid parser. The LLM requires both date AND time, so date-only inputs like `"12/05/2026"` returned `"AMBIGUOUS: falta hora"`. The old regex pipeline handled these via `datetime.strptime(new_date_str, "%d/%m/%Y")`.

**Root cause chain:**
1. Hybrid refactor replaced regex-first with LLM-first date parsing in `reschedule_appointment_tool`
2. `parse_datetime_llm` prompt demands time → date-only inputs return "AMBIGUOUS: falta hora"
3. `HybridParser.parse()` fallback condition `value is None AND error is None` blocks code fallback when LLM returns an error (non-None error)
4. Error propagates to LLM → LLM retries with same args → hits the 3-failure limit → generic "dificultades técnicas"

**Fixes:**
1. `app/core/hybrid/base.py:83` — fallback condition: `value is None and error is None` → `value is None` so code fallback runs on ANY LLM failure (not just technical crashes like empty/garbled output)
2. `app/agents/tools.py:1052-1087` — two-stage date parsing: numeric formats first (regex, no LLM cost), then hybrid parser for natural language (falls back to regex via the fix above)

| Input | Before fix | After fix |
|-------|-----------|-----------|
| `"12/05/2026"` | ❌ LLM says "falta hora" | ✅ regex `%d/%m/%Y` |
| `"2026-05-12"` | ❌ Same | ✅ regex `%Y-%m-%d` |
| `"12/05/26"` | ❌ Same | ✅ regex `%d/%m/%y` |
| `"viernes"` | ❌ Same | ❌ Still broken (both parsers need time) |
| `"12/05/2026 15:00"` | ✅ Works | ✅ Works |

### Sprint 29 — Auto-clean test user's Google Calendar on deploy (May 16, 2026)

**Commit:** `6cfe4eb`

**Problem:** After every deploy, test phone `5493754455340` had stale appointments and Google Calendar events from previous test sessions. Repeated deployments accumulated calendar clutter — no way to test appointment flows cleanly.

**Fix:** Added a block in `app/main.py:lifespan()` after the existing Redis context reset:
1. Queries `User` by `whatsapp_phone` (defaults to same `RESET_PHONE_ON_STARTUP` env var)
2. Finds all appointments for that user with a non-null `calendar_event_id`
3. Calls `calendar_service.cancel_visit(event_id)` to remove each from Google Calendar
4. Marks each appointment `status = "cancelled"` and commits
5. Graceful if calendar not configured (catches exception, logs warning)

**Audit:** Sub-worker code audit passed (0 CRITICAL/HIGH issues in new code). Pre-existing findings noted: debug endpoint leaks verify token (unrelated).

### Sprint 30 — V2 search: add zone-drop fallback for landmark searches (May 28, 2026)

**Commit:** `392c44c`

**Problem:** User searched "departamentos cerca de UNAM, 1 dormitorio" — bot found 1 terreno and 1 casa near UNAM instead of showing the 12 departamentos de 1 dormitorio available in other zones. The Fallback 1 kept `operation + zona` but dropped `tipo` and `dormitorios`, so it surfaced irrelevant property types near the landmark.

**Root cause:** `app/tools/v2/search_properties.py` had only one fallback path: drop tipo/budget/bedrooms, keep operation+zona. When a landmark had zero matching properties of the requested type, it offered unrelated types near that landmark instead of matching types elsewhere.

**Fix:** Added **Fallback 2** in `search_properties.py` (lines 108-139):
- After Fallback 1 finds nearby properties, checks if ANY match the user's `mapped_tipo`
- If not → runs `operation + tipo + dormitorios` (NO zona) → shows matching types in all of Oberá
- Message: "No encontré X específicamente en ZONA. Pero hay N X en otras zonas de Oberá"

**Test results (4/4 pass):**
| Test | Result |
|------|--------|
| depto cerca UNAM, 1 dorm | Fallback 2 → 6 deptos in other zones ✅ |
| depto cerca UNAM (no dorm) | Fallback 2 → 12 deptos in other zones ✅ |
| properties near Terminal | Direct match (2 deptos) → no fallback needed ✅ |
| casa cerca UNAM | Direct match (1 casa) → no fallback needed ✅ |

**Files changed:** `app/tools/v2/search_properties.py` (+53/-20 lines)
- Moved `tipo_map` to module level so it's available in fallback logic
- Added `mapped_tipo` early computation
- Added Fallback 2 check + query + response format
