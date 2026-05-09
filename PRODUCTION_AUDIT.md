# InmuebleBot — Production Readiness Audit Report
**Date:** 2026-05-08  
**Scope:** Full codebase (~17,873 LOC across 55+ Python modules, 6 React JSX files)  
**Methodology:** 3 parallel specialists (Security, Backend Logic, Ops) reviewing independently

---

## ✅ Fixed Across May 2026 Sprints

### Multi-Agent Fix Sprint (May 8)

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| C1 | Timezone bug (appointments 3h off) | 🔴 CRITICAL | ✅ FIXED |
| C12 | No exception handlers | 🔴 CRITICAL | ✅ FIXED |
| H6 | Webhook fire-and-forget loses messages | 🟠 HIGH | ✅ FIXED |
| C9/C10 | Celery dead code | 🔴 CRITICAL | ✅ REMOVED |
| M1 | NFKD destroys Spanish names | 🟡 MEDIUM | ✅ FIXED |
| H4 | Engine never disposed in property_service | 🟠 HIGH | ✅ FIXED |
| Calendar | Timezone mismatch, dead code, blocking sync, no OAuth refresh, admin not synced | 🟠 HIGH | ✅ ALL FIXED |

### Architecture Sprint 3 (May 9-10)

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| M4 | Engine created per call in tools.py (connection pool churn) | 🟡 MEDIUM | ✅ FIXED — Global async_session_factory replaces 8 ad-hoc engines |
| M7 | Engine never disposed in memory.py | 🟡 MEDIUM | ✅ FIXED — Uses global pool, no ad-hoc engines |
| H2 | Forced search bypass causes double execution | 🟠 HIGH | ✅ FIXED — Forced search removed entirely |
| H7 | _processed_ids unbounded memory leak | 🟠 HIGH | ✅ FIXED — In-memory fallback added (non-leaking) |
| H1 | State machine TOCTOU race | 🟠 HIGH | ✅ FIXED — Per-user Redis lock (prior sprint) |

### Google Calendar Auth Sprint (May 10)

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| C4 | Google OAuth credentials on disk (live refresh token) | 🔴 CRITICAL | ✅ FIXED — Now loads from Render Secret Files or env vars |
| C16 | Missing GOOGLE_* env vars in render.yaml | 🔴 CRITICAL | ✅ FIXED — GOOGLE_TOKEN_JSON + GOOGLE_CREDENTIALS_JSON added |
| — | Calendar service no retry on credential failure | 🟠 HIGH | ✅ FIXED — reset() method + double retry in service property |

---

## 🔴 TIER 1 — CRITICAL (Fix Immediately — System-Breaking or Data-Losing)

### C1. Appointments 3 Hours Off Due to Timezone Bug
- **Files:** `app/services/appointment_service.py:84,474-478` vs `:426-431`
- **Bug:** `_ensure_timezone()` stamps naive datetimes as **UTC**. But Argentina (primary market) is **UTC-3**. A user saying "mañana a las 15:00" gets stored as 15:00 UTC = 12:00 Argentina.
- **Worse:** `_check_conflict()` at line 426-431 uses **different logic** (assumes Argentina time). So conflict detection disagrees with actual storage.
- **Impact:** Every appointment scheduled through the bot is 3 hours off. Users arrive at wrong time. Conflict detection is broken.
- **Fix:** Use `America/Argentina/Buenos_Aires` timezone throughout. Never assume UTC for naive datetimes.

---

### C2. `force=True` on Seed Destroys All Properties on Every Dev Restart
- **Files:** `app/db/seed.py:96-100`, `app/main.py:62-68`
- **Bug:** `main.py` lifespan calls `seed_properties(force=True)` when `ENVIRONMENT=development`. Inside seed.py, `force=True` does `DELETE FROM properties` then re-inserts from seed JSON.
- **Impact:** Every `uvicorn --reload` in development wipes ALL manually added properties (via admin dashboard). Data loss on every hot reload.
- **Fix:** Only seed if table is empty. Remove `force` parameter entirely. Use `INSERT ... ON CONFLICT DO NOTHING`.

---

### C3. Hardcoded Production Database & Redis Credentials in render.yaml
- **File:** `render.yaml:33,39`
- **Bug:** Production DB password `saL1PlnMCey0qrxY0fd0LDmjqRl5BDeY` and Redis password `VG3EM8cX2C4M3LLQuA4dd00VMhM7vq3z` hardcoded in tracked YAML file.
- **Impact:** Anyone with git access has full read/write to production database. Complete data breach.
- **Fix:** Use Render secret env vars, not hardcoded values. Immediately rotate both passwords.

---

### C4. Google OAuth Credentials on Disk (Live Refresh Token)
- **File:** `credentials/token.json`, `credentials/client_secrets.json`
- **Bug:** Live Google Calendar OAuth credentials on disk: `client_secret: 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`, `client_id: 846638360420-...`, and a **valid refresh token** that can regenerate access tokens.
- **Impact:** Anyone with filesystem access can control the Google Calendar associated with the bot.
- **Fix:** Revoke the OAuth token in Google Cloud Console immediately. Re-generate with proper secret management. Add `credentials/*` to `.dockerignore`.

---

### C5. Live API Keys in old.env (Tracked in Git)
- **File:** `old.env` (tracked in git history)
- **Bug:** Contains `MINIMAX_API_KEY=sk-or-...`, `GEMINI_API_KEY=AIzaSy...7fqo`, `DATABASE_URL` with local credentials.
- **Impact:** Keys in git history are compromised. The Gemini key `AIzaSy...7fqo` is also in the live `.env`.
- **Fix:** Immediately revoke ALL keys listed in old.env. Remove the file. Add to `.gitignore` retroactively using `git filter-branch` or BFG.

---

### C6. No Auth on `/admin/debug/users` — Leaks DB Schema + User Data
- **File:** `app/api/routes/admin.py:89-109`
- **Bug:** `GET /admin/debug/users` has ZERO authentication — missing `Depends(verify_admin_api_key)`. Returns DB table names, first user record (phone, name, score).
- **Impact:** Unauthenticated info disclosure. Any bot or scanner hitting the production endpoint gets DB schema and user details.
- **Fix:** Add `Depends(verify_admin_api_key)` to the endpoint.

---

### C7. Default `ADMIN_API_KEY` = `"admin-secret-key"` — Admin Panel Wide Open
- **Files:** `app/core/config.py:144`, `.env:72`, `dashboard/.env:8`
- **Bug:** Default `ADMIN_API_KEY` = `"admin-secret-key"` in code. Live `.env` has `your-secure-admin-key-here` (same as `.env.example`). Dashboard config confirms the key was never changed.
- **Impact:** All admin CRUD endpoints (leads, properties, appointments) are accessible with a well-known default key.
- **Fix:** Generate a secure random key. Set it in Render dashboard env vars. Validate it's been changed on startup (warn if default).

---

### C8. `/webhook/debug` Leaks WhatsApp Verify Token
- **File:** `app/api/routes/webhook.py:186-196`
- **Bug:** Unauthenticated `GET /webhook/debug` returns `{"configured_token": "inmueblebot2026_secreto", ...}`.
- **Impact:** An attacker can discover the verify token, register a fake webhook with Meta, and intercept/send messages.
- **Fix:** Remove the debug endpoint or add strong auth. Webhook verify token should NEVER be exposed.

---

### C9. Celery Tasks Use `await` in Sync Functions — Will Crash
- **File:** `app/tasks/followups.py:40,57`, `app/tasks/reminders.py:86,93`
- **Bug:** `await property_service.get_property_details(...)` called inside sync `@celery_app.task` functions. Celery tasks are NOT async by default.
- **Impact:** These tasks will raise `SyntaxError` or `RuntimeError` when executed. All follow-ups, reminders, and maintenance are dead code.
- **Fix:** Use `asyncio.run()` wrapper for each `await` call, or use Celery's async task support.

---

### C10. `app.db.repository.database` Import Path Doesn't Exist
- **Files:** `app/tasks/followups.py:23,31,82,89,133,177`, `app/tasks/lead_scoring.py:31,44,80`, `app/api/deps.py:3,7`
- **Bug:** Imports `from app.db.repository.database import SessionLocal` but the path is `app/db/repository.py` (single file, not a package).
- **Impact:** `ModuleNotFoundError` on any import. All Celery tasks and admin deps are dead code.
- **Fix:** Fix import paths to `from app.db.repository import SessionLocal` or create the correct module structure.

---

### C11. Loguru `serialize=True` Format Incompatible with Render Log Aggregation
- **File:** `app/main.py:24`
- **Bug:** `serialize=True` outputs loguru's internal JSON format (`{text: "...", record: {...}}`). Render expects standard structured JSON or plaintext.
- **Impact:** Logs are unreadable in Render dashboard. Cannot search, filter, or alert on log content.
- **Fix:** Use a custom JSON formatter instead of `serialize=True`.

---

### C12. No FastAPI Exception Handlers — Raw 500s Escalate to Meta
- **File:** `app/main.py` (missing)
- **Bug:** No `@app.exception_handler(Exception)`. Unhandled errors return FastAPI's default 500. Meta receives HTTP 500 and retries, compounding failures.
- **Impact:** Users get no response on crashes. Meta retries amplify the load. No structured error tracking.
- **Fix:** Add global exception handler with Sentry/rollbar integration and friendly fallback response.

---

### C13. Render Free Plan = No Zero-Downtime Deploys
- **File:** `render.yaml:25` (`plan: free`)
- **Bug:** Free tier stops the service before starting the new version. Brief outage (5-30s) on every deploy.
- **Impact:** WhatsApp messages sent during deploy window are lost (Meta retries for ~30s then gives up).
- **Fix:** Upgrade to at least Starter plan ($7/mo) for zero-downtime deploys.

---

### C14. Redis Publicly Accessible (`0.0.0.0/0`) in render.yaml
- **File:** `render.yaml:17-19`
- **Bug:** `ipAllowList: [{source: "0.0.0.0/0", ...}]` — Redis is accessible from the entire internet.
- **Impact:** Anyone who knows the Redis URL (hardcoded in render.yaml!) can connect. Session data, conversation context, intent cache all exposed.
- **Fix:** Restrict to Render internal network. Redis URLs should use secret env vars, not hardcoded YAML.

---

### C15. Streamlit `asyncio.run()` Inside Running Event Loop
- **File:** `frontend/chat_ui.py:120,231,243,295-296,429`
- **Bug:** Streamlit runs its own asyncio event loop. Calling `asyncio.run()` from inside it raises `RuntimeError: cannot be called from a running event loop`.
- **Impact:** The Streamlit chat UI crashes on any interaction. The entire test interface is broken.
- **Fix:** Use `asyncio.get_event_loop().run_until_complete()` or `nest_asyncio.apply()`.

---

### C16. Missing Env Vars in render.yaml
- **File:** `render.yaml:31-39`
- **Bug:** Missing: `ADMIN_API_KEY`, `SECRET_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `MINIMAX_API_KEY`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- **Impact:** Deployment on Render will use all default values. No LLM keys = bot never responds. `SECRET_KEY=change-me-in-production`.
- **Fix:** Add all required env vars as secret references.

---

### C17. Celery Broker URL `rediss://` Not Configured for Celery
- **File:** `config/celery_settings.py:18`
- **Bug:** `broker=settings.REDIS_URL.replace("redis://", "redis://")` — no-op replacement. Render's Redis uses `rediss://` (TLS). Celery with `rediss://` needs `ssl_cert_reqs=CERT_NONE` or cert config.
- **Impact:** Celery cannot connect to Redis in production. All background tasks broken.
- **Fix:** Add proper SSL config for Celery broker URL.

---

## 🟠 TIER 2 — HIGH (Fix Soon — Causes Incorrect Behavior or Data Loss in Edge Cases)

### H1. State Machine Has TOCTOU Race on Concurrent Messages
- **File:** `app/core/state_machine.py:193-224`, `app/api/routes/webhook.py:270`
- **Bug:** `set_state()` does READ-then-WRITE without Redis WATCH/MULTI/EXEC. `webhook.py:270` uses `asyncio.ensure_future` allowing concurrent processing.
- **Impact:** Two messages from same user milliseconds apart can overwrite each other's state transitions.
- **Fix:** Use Redis locks or `WATCH` key for atomic state transitions. Add user-level semaphore.

### H2. Forced Search Bypass Causes Double Execution
- **File:** `app/agents/real_estate_agent.py:111-194`
- **Bug:** When forced search triggers on iteration 0, it injects fake tool messages and `continue`s. On iteration 1, the LLM sees the injected result and may call `search_properties` AGAIN.
- **Impact:** Wastes LLM calls, DB queries, and confuses context. Under load, this doubles search traffic.
- **Fix:** After forced search, skip the remaining LLM loop entirely (set `response_text` from result and break).

### H3. `PropertyRepository.get()` Types `id` as UUID but Property has Integer PK
- **File:** `app/db/repository.py:27`
- **Bug:** `async def get(self, id: UUID)` — all callers pass ints. Works only because SQLAlchemy handles type coercion. Breaks if any code actually passes UUID.
- **Impact:** Latent crash. Wrong IDE warnings. If new code uses the typed UUID, property lookups silently fail.
- **Fix:** Make `get()` accept `Union[int, UUID]` or create `get_by_id(Union[int, UUID])`.

### H4. Engine Never Disposed in `property_service.get_property_details()`
- **File:** `app/services/property_service.py:295-296`
- **Bug:** `engine.dispose()` is after `return` inside `async with async_session_factory() as session: ... return prop`. The `dispose()` call is **dead code**.
- **Impact:** Every call to `get_property_details()` creates a new engine+pool that's never cleaned up.
- **Fix:** Move `engine.dispose()` before the return, or reuse the global `async_session_factory`.

### H5. Unauthenticated WhatsApp Webhook (Signature Verification Skipped)
- **File:** `app/api/routes/webhook.py:237-241`
- **Bug:** `# Note: We'd need raw body for full verification. For now, skip and trust Meta's network` — HMAC verification is a `pass`.
- **Impact:** Any attacker who knows the webhook URL can send fake WhatsApp messages. No origin verification.
- **Fix:** Implement proper HMAC signature verification using raw request body (`request.body()` before `request.json()`).

### H6. Webhook Fire-and-Forget Loses Messages on Crash
- **File:** `app/api/routes/webhook.py:270`
- **Bug:** `asyncio.ensure_future(process_messages(...))` — returns 200 OK before processing. If `process_messages` crashes, error is logged but Meta considers message delivered. No retry, no dead-letter queue.
- **Impact:** Users send messages that disappear silently.
- **Fix:** Add `try/except` wrapper around `ensure_future` with error logging and (optional) queue-based retry.

### H7. `_processed_ids` Unbounded Memory Leak
- **File:** `app/api/routes/webhook.py:34-55`
- **Bug:** `Dict[str, float]` grows unbounded. Prunes at 1000+ entries but 1000 unique message IDs in 5 minutes is possible under load.
- **Impact:** Slow memory leak. Process OOM after sustained traffic.
- **Fix:** Use `cachetools.TTLCache` or Redis-based dedup.

### H8. Webhook No-Auth Endpoints Leak Info
- **File:** `app/api/routes/webhook.py:172-196`
- **Bug:** `/webhook/verify` and `/webhook/debug` return token configuration info without authentication.
- **Fix:** Remove debug endpoints in production or add IP whitelist.

### H9. Docker Healthcheck Uses `curl` Not in Slim Image
- **File:** `docker-compose.yml:74`
- **Bug:** `test: ["CMD", "curl", "-f", "http://localhost:8000/health"]` — `python:3.12-slim` does NOT include `curl`.
- **Impact:** Docker healthcheck always fails. Container appears unhealthy.
- **Fix:** Use `CMD-SHELL` with `wget` or `python -c`.

### H10. No CI/CD Pipeline
- **File:** Missing (no `.github/`)
- **Bug:** No automated testing, linting, or type checking on push. Every deploy relies on manual verification.
- **Fix:** Add GitHub Actions workflow running ruff → mypy → pytest on push/PR.

### H11. Cross-Region Latency (Oregon → Frankfurt DB)
- **File:** `render.yaml:8` (region: oregon) vs `render.yaml:33` (frankfurt-postgres.render.com)
- **Bug:** App runs in Oregon (US West) but DB is in Frankfurt (Europe). ~150ms added to every query.
- **Impact:** Combined with LLM latency, webhook may exceed Meta's 5-second timeout.
- **Fix:** Move all services to same region.

### H12. Celery Beat Task `maintenance` Not in Celery Include List
- **File:** `config/celery_settings.py:20-24`
- **Bug:** Beat schedule references `app.tasks.maintenance.cleanup_old_sessions` but `maintenance` is not in `CELERY_IMPORTS`.
- **Impact:** Maintenance task never executes (even if Celery were working).
- **Fix:** Add `"app.tasks.maintenance"` to `include` list.

---

## 🟡 TIER 3 — MEDIUM (Fix When Working on Related Code — Causes Suboptimal Behavior)

| # | File | Lines | Issue |
|---|------|-------|-------|
| M1 | `sanitizer.py:25` | NFKD Unicode normalization destroys Spanish accents: `ñ`→`n`, `ó`→`o`. User names stored incorrectly. |
| M2 | `sanitizer.py:88` + `repository.py:186` | LIKE wildcards `%` and `_` not escaped in location search. Can bypass location filter. |
| M3 | `memory.py:96-99` | New `redis.Redis` instance per call, orphaned on retry failures. Client objects accumulate. |
| M4 | `tools.py:316-323,876-883` | Engine created per call in `get_property_details`, `get_property_images`, `schedule_visit`. Connection pool churn. |
| M5 | `appointment_service.py:436` | `int(property_id)` on non-int raises ValueError (latent — not triggered by current callers) |
| M6 | `classifier.py:253-254` | Duplicate return statement (dead code) |
| M7 | `memory.py:309-367,380-382` | `create_async_engine` per call in `update_user_preferences` + `get_user_preferences` — never disposed. Leaks connections on every message. |
| M8 | `pyproject.toml` vs `requirements.txt` | `psycopg2-binary` and `streamlit` missing from pyproject.toml |
| M9 | `dashboard/package.json` | No `package-lock.json` — non-deterministic builds |
| M10 | `render.yaml` | Celery worker/beat config commented out. Tasks defined but never run. |
| M11 | `config.py:81` | `DEBUG=True` by default. If accidentally omitted in production, tracebacks leak. |
| M12 | `docker-compose.yml:27` | PostgreSQL port 5432 exposed to host with default `postgres:postgres` credentials |
| M13 | `docker-compose.yml:60-62` | Bind mount of `app/` and `credentials/` — development pattern that leaks into production mindset |
| M14 | `docker-compose.yml:98` | Streamlit port mapping `8502:8501` wrong (should be `8502:8502`) |
| M15 | `main.py:126-133` | Health check doesn't verify PostgreSQL connectivity |
| M16 | `webhook.py:28` | webhook.py uses stdlib logger instead of loguru (inconsistent JSON output) |
| M17 | `admin.py:387-392` | `MAX(id)+1` race on concurrent admin property creates |
| M18 | `Dockerfile:56` | `EXPOSE 8000 8080` — port 8080 unused and confusing |
| M19 | `admin.py:247-248` | Full traceback disclosure in error responses |

---

## Summary

| Tier | Count | Description |
|------|-------|-------------|
| 🔴 **CRITICAL** | 17 | Data loss, credential exposure, broken core features, exploitable vulnerabilities |
| 🟠 **HIGH** | 12 | Race conditions, silent failures, incorrect behavior, operational gaps |
| 🟡 **MEDIUM** | 19 | Code quality, resource management, missing tests, config drift |
| **TOTAL** | **48 issues** | |

### Top 5 Actions for Immediate Production Readiness

1. **🔴 Rotate ALL exposed credentials** (render.yaml DB/Redis passwords, old.env API keys, Google OAuth token, WhatsApp access token, admin API key). Every credential in render.yaml, old.env, and .env must be considered compromised.

2. **🔴 Fix the timezone bug** (`appointment_service.py:_ensure_timezone`) — Argentina is UTC-3, not UTC. Every appointment is 3 hours off.

3. **🔴 Fix seed_properties force mode** (`main.py:65-66`, `seed.py:96-100`) — stop wiping data on dev restart. Seed only when table is empty.

4. **🔴 Add auth to `/admin/debug/users`** and remove `/webhook/debug` — these leak sensitive info without authentication.

5. **🔴 Fix Celery dead code** (`app.db.repository.database` import, `await` in sync tasks, broker TLS config, missing includes) — or remove Celery entirely if background tasks are unneeded.
