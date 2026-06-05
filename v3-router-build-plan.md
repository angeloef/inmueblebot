<!-- v3-router-build-plan.md — Phased, agent-executable build plan for the V3 multi-tenant router. Author: Hermes Agent. Date: 2026-06-04 -->
# InmuebleBot V3 — Multi-Tenant Router Build Plan

> **Companion to:** [`router-v2-architecture-review.md`](router-v2-architecture-review.md) (the *why*). This doc is the *how* — a phased, checkbox-style build plan written to be executed by **Claude Code (Opus 4.8)** one phase at a time.
> **Outcome:** A production-ready, **true multi-tenant** V3 chatbot that is more intelligent and makes fewer mistakes than V2, switchable from the dashboard (V1 / V2 / V3), deployable to Render with **zero data loss** and a one-click rollback.
> **Date:** 2026-06-04 · **Author:** Hermes Agent

---

## 0. Read-me-first — Decisions locked for this build

These were confirmed with the product owner. **Do not re-litigate them; build to them.**

| # | Decision | Implication for the build |
|---|---|---|
| D1 | **True multi-tenant SaaS** | Shared-schema + `tenant_id` on every tenant-scoped table; Postgres RLS as safety net; data model must support future self-serve signup + billing. |
| D2 | **Tenant routing = one Meta app, many numbers** | Inbound webhook resolves tenant by `phone_number_id`. Each tenant row stores `waba_id` + `phone_number_id` + access token. |
| D3 | **Adopt Alembic** | Replace the ad-hoc startup raw-SQL migrations with versioned migrations. Baseline = current prod schema; first real migration = multi-tenancy + backfill default tenant. |
| D4 | **Dashboard 3-way router switch** | Extend the existing `bot_settings` mechanism (`use_v2_router`) to `active_router ∈ {v1,v2,v3}`. Webhook dispatches accordingly. Owner flips to V3 **manually** when 100% done. |
| D5 | **Promotion is manual + owner-tested** | No automated promotion gate. But **build the eval harness** anyway — the owner runs the 150-conversation suite + manual tests before flipping. Harness is advisory, not blocking. |
| D6 | **SaaS plumbing now = admin-provisioned tenants only** | Tenant CRUD via the dashboard. The existing test account = the default tenant. Self-serve signup (Inmobot landing page) + billing are **out of scope** for V3 — but the schema must not block them later. |
| D7 | **Single model: `gpt-5.4-mini` everywhere** | Tiering is permanently off. No stronger model anywhere — including the judge. Cost control comes from **fewer calls + prompt caching + structured outputs**, not bigger models. |
| D8 | **Scope frozen** | Real estate, WhatsApp, Spanish (`es-AR`). No web widget, no new vertical, no new language. Effort goes to **quality + multi-tenancy**. |

---

## 1. How the implementing agent should work (conventions)

**Read these before touching code, every session:**
- `router-v2-architecture-review.md` — the findings this plan implements (R1–R10).
- `ARCHITECTURE.md` — graph-derived system map.
- `multi_agent_chatbot_best_practices.md` — prompt/engineering playbook (note: §4.6 negative-rule ratio, §2.2 end-loading).
- This file — the phase you're on.

**Working rules:**
1. **One phase per branch.** Branch name `v3/phase-N-slug`. Open a PR per phase. Never commit straight to `main`.
2. **V2 must keep working at all times.** Until Phase 7 cutover, `active_router` defaults to `v2`. Every phase ends with V2 still green.
3. **After every phase, run the eval harness** (Phase 0 builds it) and paste the score delta into the PR description.
4. **Respect the compatibility contract** (§3). V3's adapter must return the exact dict shape `v2_adapter.process_turn_v2` returns, or the webhook + WhatsApp sender break.
5. **Commit boundaries:** one logical task (a checkbox below) ≈ one commit. Keep diffs reviewable.
6. **Tenant safety is non-negotiable.** Any new query touching tenant data must be tenant-scoped. Add a cross-tenant test that asserts zero leakage (see Phase 1).
7. **Cost discipline:** every LLM call must be justified. Default to **one** understanding call + **one** synthesis (or fold them). Structured outputs (`strict: true` json_schema) replace schema-in-prompt. Order prompts **static-first** so OpenAI prompt caching applies.
8. **Don't delete V2 files** until Phase 7. Build V3 in `app/routers/v3/` and `app/agents/v3/`.

**Definition of done for a task:** code + test + the acceptance criterion in that phase met + eval harness not regressed on unrelated flows.

---

## 2. Target architecture (V3)

```
WhatsApp (Meta, many phone numbers under one app)
   ↓  webhook: resolve tenant by phone_number_id  →  set tenant context (ContextVar + DB session GUC)
app/api/routes/webhook.py
   ↓  _resolve_active_router(tenant)  →  {v1 | v2 | v3}
app/routers/v3/adapter.py            (drop-in dict contract, == v2_adapter)
   ↓
app/routers/v3/engine.py  ──►  ONE schema-guided LLM pass (strict json_schema, gpt-5.4-mini)
   │     input:  static system prompt (cached)  +  tenant policy  +  compact state JSON (last)
   │     output: { belief_delta, intent, action, tool_calls[], missing_slot, response_plan, confidence }
   │
   ├── deterministic SAFETY gates (pre-engine): emergency · human-request · out-of-scope · /reset
   ├── deterministic EXECUTION layer: runs the tool_calls the engine chose (code owns side-effects)
   ├── scheduling/ : explicit FSM (single advance(), single booking call site)
   ├── knowledge/  : RAG-grounded answers (pgvector over tenant property + FAQ docs)
   └── guard/      : LLM rubric judge (gpt-5.4-mini), gated to low-confidence/critical turns only
   ↓  persist turn (tenant-scoped)  ·  emit structured metrics (router_label, action, latency, tokens, cache_hit)
Redis working memory (key namespaced by tenant_id + session)
```

**The inversion vs V2:** understanding lives in **one structured LLM call**, not 15 ordered regex gates. Code keeps only (a) safety gates and (b) side-effects. This is the core of R1/R2.

---

## 3. Compatibility contract (must not break)

V3 is additive until cutover. These interfaces are frozen:

- **Adapter return dict** — `process_turn_v3(phone, user_message, media_url, bsuid, tenant)` must return the same keys as `v2_adapter.process_turn_v2`:
  `response_text, tools_used, rich_content{images,caption,selected_property_id,search_criteria,active_intents[,response_plan]}, confidence, router_label, latency_ms[, messages]`.
- **Router switch** — keep `bot_settings` as the source of truth. Add key `active_router`. `_resolve_use_v2_router` becomes `_resolve_active_router` returning `"v1"|"v2"|"v3"` (back-compat: if only `use_v2_router` is set, map true→v2/false→v1).
- **Dashboard settings API** — `/admin/settings` GET/PATCH (`dashboard/src/api.js` `settingsApi`) stays; add `active_router` to its payload.
- **Tools** — keep the `app/tools/v2/registry.py` names/signatures. V3 may add a tenant-scoped layer *around* them, not rename them. WhatsApp sender + dashboard depend on tool names (`get_property_images`, etc.).
- **DB** — additive only (new tables, new nullable columns + backfill). No destructive changes to `conversations`, `messages`, `properties`, `appointments`, `leads`, `faqs`, `cobranzas`.
- **Simulate endpoint** — `/admin/simulate` (`app/api/routes/simulate_v2.py`) must accept an optional `router` and `tenant` param so the eval harness can target V3 for a specific tenant.
- **Render** — single web service + Postgres + Redis (`render.yaml`). No new always-on service required by V3 (pgvector is an extension on the existing DB).

---

## 4. The phases

> Each phase: **Goal → Tasks (checkboxes) → Key files → Acceptance criteria.** Phases are ordered; later phases assume earlier ones merged.

---

### Phase 0 — Foundations & Safety Net
**Goal:** Make change *safe and measurable* before changing behavior. No user-visible change.

**Tasks**
- [ ] **Adopt Alembic.** Wire `alembic/env.py` to `app/db/base.Base.metadata` + `settings.resolved_database_url`. Generate a **baseline** migration that matches the *current* prod schema (autogenerate, then hand-verify against the live Render DB — remember the schema today is created by `admin.py:_run_startup_migration`, so reconcile any drift).
- [ ] **Stop creating tables at startup blindly.** Gate `_run_startup_migration` behind `RUN_LEGACY_STARTUP_MIGRATION` (default true for now); the goal is to run `alembic upgrade head` on deploy instead. Add an `alembic upgrade head` step to the Docker entrypoint / `run.sh`.
- [ ] **Build the eval harness** (`tests/eval/`):
  - Parser for `angelo-hard-test-conversations-150.md` → structured multi-turn cases.
  - Runner that replays each case against `/admin/simulate` (with `reset=true`, target `router` + `tenant`).
  - **Rubric LLM-judge** (gpt-5.4-mini) scoring per turn: *task-completion*, *faithfulness/no-hallucination*, *no-repeat/loop*, *tone*. Use a strict-JSON rubric; keep the rubric prompt versioned. (Judge bias is real — keep the rubric deterministic and log raw turns for manual spot-check.)
  - Output a scorecard `tests/eval/reports/<git-sha>.json` + a markdown diff vs the V2 baseline.
- [ ] **Snapshot the V2 baseline** score now and commit it as `tests/eval/baseline-v2.json`.
- [ ] **Observability scaffolding.** Add a structured per-turn log/metric: `tenant_id, router, router_label, action, tools, latency_ms, prompt_tokens, completion_tokens, cache_hit, confidence, judge_score`. One JSON line per turn (so it's greppable in Render logs).
- [ ] **Secrets hardening.** The committed `render.yaml` contains a live Postgres URL **with password**. Move it to a Render env var / secret, rotate the DB password, and replace the literal with `sync: false`. (Do this early — it's a real exposure.)

**Key files:** `alembic/`, `alembic.ini`, `app/db/base.py`, `app/main.py`, `run.sh`/`Dockerfile`, `app/api/routes/admin.py` (`_run_startup_migration`), `app/api/routes/simulate_v2.py`, `tests/eval/*`, `render.yaml`.

**Acceptance:** `alembic upgrade head` reproduces current schema on a fresh DB; eval harness runs end-to-end and reproduces a V2 baseline score; turn metrics visible in logs; no secret left in git.

---

### Phase 1 — Multi-Tenancy Foundation
**Goal:** Introduce true tenant isolation **while V2 keeps serving the default tenant**. This is the largest data-layer change.

**Tasks**
- [ ] **`tenants` table** (Alembic migration): `id (uuid pk)`, `slug`, `display_name`, `company_name`, `business_hours`, `timezone (default America/Argentina/Cordoba)`, `zones (jsonb)`, `branding (jsonb)`, `waba_id`, `phone_number_id (unique, indexed)`, `wa_access_token (encrypted)`, `plan`, `status`, `created_at`. Design for billing later (nullable `plan`, `status`).
- [ ] **Per-tenant bot config.** Move `bot_settings` from a global key/value table to **tenant-scoped** (`tenant_id` column) — or add a `tenant_settings` table. `active_router`, `company_name`, `business_hours`, prompt overrides live here. Keep a global fallback row for safety.
- [ ] **Add `tenant_id` (uuid, FK→tenants, indexed)** to every tenant-scoped table: `conversations`, `messages`, `properties`, `appointments`, `leads`, `faqs`, `cobranzas`, `user_episodes`, `users`. Nullable first.
- [ ] **Backfill migration:** create the **default tenant** from current env (`COMPANY_NAME`, etc. + the existing WhatsApp number), set every existing row's `tenant_id` to it, then set columns `NOT NULL`.
- [ ] **Postgres RLS** (safety net, not sole control): enable RLS on tenant-scoped tables; policy `tenant_id = current_setting('app.current_tenant_id')::uuid`. The app DB role must **not** be `BYPASSRLS`.
- [ ] **Transaction-scoped tenant context.** In `app/db/session.py`, on each request/session, `SELECT set_config('app.current_tenant_id', :tid, true)` (the `true` = transaction-local — required so Render's connection pooler can't leak tenant state between pooled connections; see CVE-2024-10976). Add a `ContextVar` for the app layer too.
- [ ] **Tenant resolution in the webhook.** Parse `entry[].changes[].value.metadata.phone_number_id` → look up tenant → set DB GUC + ContextVar for the whole turn. Reject/park messages from unknown numbers.
- [ ] **Tenant-scope the tools + memory.** `search_properties`, `get_faq_answer`, appointment tools, etc. filter by current tenant. Redis working-memory keys become `wm:{tenant_id}:{session_id}` (`app/memory/working.py`); same for specialist-state and episodic keys.
- [ ] **Cross-tenant isolation tests** (`tests/test_tenant_isolation.py`): seed two tenants, assert every read path returns **zero** rows for the other tenant (tools, conversation history, appointments, dashboard endpoints).
- [ ] **Dashboard: tenant provisioning.** Admin screen to create/edit tenants (name, branding, zones, `phone_number_id`/`waba_id`/token, business hours). The current test account becomes the default tenant. Scope all existing admin list endpoints (`/admin/leads`, `/admin/properties`, `/admin/appointments`, `/admin/conversations`) by selected tenant.

**Key files:** `alembic/versions/*`, `app/db/models/*`, `app/db/session.py`, `app/api/routes/webhook.py`, `app/api/routes/admin.py`, `app/tools/v2/*`, `app/memory/working.py`, `app/core/identity.py`, `app/services/*`, `dashboard/src/*`, `tests/test_tenant_isolation.py`.

**Acceptance:** existing prod data fully attributed to the default tenant; a second seeded tenant is fully isolated (RLS + app-layer + tests prove zero leakage); inbound webhook maps `phone_number_id`→tenant; V2 still serves the default tenant unchanged.

---

### Phase 2 — V3 Skeleton & the 3-Way Switch
**Goal:** Wire a parallel V3 path end-to-end with a trivial engine, so routing/contract/switch are proven before building intelligence.

**Tasks**
- [ ] **Create `app/routers/v3/`**: `adapter.py` (mirrors `v2_adapter` dict contract), `engine.py` (stub: echoes + returns valid contract), `__init__.py`.
- [ ] **`active_router` setting.** Add to tenant settings; implement `_resolve_active_router(tenant) -> "v1"|"v2"|"v3"` (back-compat with `use_v2_router`). Update webhook dispatch (currently `~webhook.py:536`) to a 3-way branch.
- [ ] **Dashboard config: 3-way selector.** Replace the V2 on/off toggle with a V1/V2/V3 segmented control in the Config section; persist via `/admin/settings` (`active_router`). Show which router is live per tenant.
- [ ] **Simulate endpoint:** accept `router=v3` + `tenant` so the eval harness + manual tests can hit V3.
- [ ] **Contract parity test:** assert `process_turn_v3` returns the identical key set as `process_turn_v2` for a fixed input.

**Key files:** `app/routers/v3/*`, `app/api/routes/webhook.py`, `app/api/routes/admin.py`, `app/api/routes/simulate_v2.py`, `dashboard/src/*` (Config view + `api.js`).

**Acceptance:** flipping the dashboard to V3 routes live traffic to the stub and back to V2 with no errors; `/admin/simulate?router=v3` works; contract parity test green.

---

### Phase 3 — Core Understanding Engine (implements R1 + R2)
**Goal:** Replace regex-extract→LLM-correct and the regex routing cascade with **one schema-guided LLM pass** that returns state + action. This is the intelligence core.

**Tasks**
- [ ] **Define the turn schema** (`app/routers/v3/schema.py`) as a strict JSON schema for OpenAI Structured Outputs (`strict: true`):
  ```jsonc
  {
    "belief_delta": { "operation": "...|null", "property_type": "...|null",
                      "zone": "...|null", "budget_max": 0, "bedrooms_min": 0 },
    "intent": "search|scheduling|knowledge|negotiation|rapport|handoff|out_of_scope",
    "action": "search|show_details|show_photos|answer_knowledge|book_step|select_property|clarify|handoff|smalltalk",
    "tool_calls": [ { "name": "...", "arguments": { } } ],
    "selected_property_id": 0,
    "missing_slot": "scheduling_day|scheduling_time|scheduling_name|null",
    "response_plan": [ { "type": "text|images", "content": "..." } ],
    "confidence": 0.0
  }
  ```
- [ ] **Belief state v5** (`app/routers/v3/belief.py`): typed, **tenant-aware**, superset of v4 fields the dashboard/state-label depend on (keep `state_label` mapping for the admin UI). Add a Redis (de)serializer; migrate v4→v5 lazily on load.
- [ ] **Engine pass** (`engine.py`): build messages as **static-first for prompt caching** — (1) static system prompt + tool schema (identical across turns → cached), (2) tenant policy block (per-tenant, semi-static), (3) recent message history, (4) **compact state JSON as the LAST message**. ⚠️ This reverses V2's bug of *prepending* dynamic context to the system prompt, which defeats caching. Call once with `response_format` = the turn schema.
- [ ] **Regex extractors → fallback only.** Keep `state_transitioner` functions, but the engine's `belief_delta` is authoritative. Run regex **only** to fill gaps when the engine returns nulls or on engine failure (hybrid degradation). Delete the `correcciones`/`_apply_belief_corrections` round-trip — it's subsumed.
- [ ] **Deterministic execution layer** (`engine.py`): take the engine's `action`/`tool_calls`, validate args (`validate_tool_args`), execute via the tenant-scoped registry, then do a **single synthesis** step only if a tool ran and the engine didn't already provide `response_plan`. (Prefer the engine emitting `response_plan` directly to save a call.)
- [ ] **Keep ONLY safety gates as pre-engine code:** emergency, explicit human-request, out-of-scope, `/ResetMemory`. Everything the V2 cascade did (refinement, narrowing, description-resolve, slot-change, multi-intent, cost-from-memory, …) is now the engine's job via `action` + context. Port each as a **schema/prompt capability + few-shot**, not a regex branch.
- [ ] **Port V2's hard-won behaviors as eval cases + prompt few-shots**, not code: read the `FIX/P/B` comments in `router.py` and `angelo-hard-test-conversations-150.md`, turn each into (a) an eval case and (b) a one-line instruction or GOOD/MALO example in the engine prompt. This is how the intelligence survives the deletion of the cascade.

**Key files:** `app/routers/v3/{schema,belief,engine,prompts}.py`, `app/agents/cs_llm_client.py` (ensure `response_format`/strict supported), `app/core/state_transitioner.py` (demote to fallback), `app/tools/v2/registry.py`.

**Acceptance:** on the eval harness, V3 ≥ V2 on task-completion and **strictly better on no-loop / no-double-ask**; a verified prompt-cache hit on the static prefix (visible in usage); the regex cascade in the V3 path is gone except safety gates.

---

### Phase 4 — Scheduling FSM + Structural Anti-Hallucination (R3 + R10)
**Goal:** Make booking deterministic and impossible to fake.

**Tasks**
- [ ] **Explicit FSM** (`app/routers/v3/scheduling/fsm.py`): states `idle → property_selected → need_day → need_time → need_name → confirm → booked`. One `advance(belief, message, engine_output) -> (response_plan, next_state)`; **one** call site for `schedule_visit`.
- [ ] **Structural `booking_succeeded`.** A turn is "booked" **iff** `schedule_visit` actually returned success — surfaced as a boolean from the execution layer. The synthesis prompt receives it and is forbidden to assert a booking otherwise. **Delete** `_FAKE_BOOKING`, `_SCHED_FAILED_MARKERS`, anti-fake reroute regex from the V3 path.
- [ ] **Availability check inside the FSM** (reuse `appointment_service.check_slot_availability`) before `confirm`; offer alternative slots on conflict.
- [ ] **Tenant-aware slots/hours** from `tenants.business_hours` + `timezone` (not hardcoded 09–12/15–18).
- [ ] **Edge cases as FSM transitions + eval cases:** slot rejection ("ese día no puedo"), name correction, mid-flow interruption (answer + keep pending), topic switch (exit), loop escape → handoff.

**Key files:** `app/routers/v3/scheduling/*`, `app/services/appointment_service.py`, `app/services/calendar_service.py`, `tests/eval/` (scheduling cases).

**Acceptance:** zero fake confirmations possible (proven by a test that makes the LLM claim success with no tool call → user never sees a confirmation); all scheduling eval cases pass; one booking call site only.

---

### Phase 5 — Grounded Knowledge / RAG (R7)
**Goal:** Knowledge & property Q&A grounded in retrieved tenant data; cut hallucination.

**Tasks**
- [ ] **Enable `pgvector`** on the Render Postgres (extension + Alembic migration). No new service.
- [ ] **Embedding index** (`app/routers/v3/knowledge/index.py`): embed per-tenant property descriptions + FAQ/policy docs with `text-embedding-3-small` (cheap). Store vectors in a tenant-scoped table; re-embed on property/FAQ create/update (hook into `property_service`/`faq_service`).
- [ ] **Retrieval-grounded knowledge specialist:** retrieve top-k tenant chunks, instruct the engine/knowledge step to answer **only** from retrieved context, else say it will confirm with a human. Optionally cite the property/FAQ.
- [ ] **Wire into engine:** when `action == answer_knowledge`, run retrieval and pass snippets in the (cached-prefix-friendly) context. Keep `get_faq_answer` tool name as the execution surface.

**Key files:** `app/routers/v3/knowledge/*`, `alembic/versions/*` (pgvector), `app/services/{property_service,faq_service}.py`.

**Acceptance:** knowledge answers cite/are grounded in tenant data; an eval case asking something *not* in the corpus yields a safe deferral, not a fabrication; embedding cost per turn is negligible (logged).

---

### Phase 6 — Response Quality, Context Hygiene & Cost (R4 + R5 + R6)
**Goal:** Best-possible prose on `gpt-5.4-mini`, minimal calls, clean context.

**Tasks**
- [ ] **Collapse the call chain.** Target **≤2–3 LLM calls/turn**: understand(+act) → optional synthesis → optional judge. Prefer the engine emitting `response_plan` so no separate synthesis is needed when no tool ran.
- [ ] **Single, end-loaded context block.** Delete the legacy imperative engine path (`_legacy_build_context_prompt`, `USE_DIRECTIVE_ENGINE=False`). Emit state **once** as compact JSON, placed last. Stop injecting history three ways (state block + recent_messages + search history) — pick the `messages[]` array as the single conversational source; keep only *derived* facts in the state JSON.
- [ ] **Honor the negative-rule ratio** (your own playbook §4.6): rewrite the engine/specialist prompts outcome-first; keep `NUNCA/CRÍTICO` ≤ ~1:10.
- [ ] **Judge gating.** Run the rubric judge only when `confidence < τ` or on critical actions (booking, handoff, price) — all on `gpt-5.4-mini`. On fail, **one** targeted regeneration (not up to 2 full reroutes like V2).
- [ ] **Prompt-caching verification.** Confirm cache hits on the static prefix in usage logs; assert the dynamic tail is the only thing changing per turn. Add `cache_hit` to metrics (Phase 0).

**Key files:** `app/routers/v3/{engine,prompts,guard}.py`, `app/core/context_aggregator.py` (retire legacy), `app/agents/cs_llm_client.py`.

**Acceptance:** median calls/turn ≤ 3 and p95 latency ≤ V2; cache-hit rate on the static prefix is high (logged); legacy context engine removed from the V3 path; judge fires only on the gated subset.

---

### Phase 7 — Hardening, Eval & Cutover
**Goal:** Prove production-readiness and switch the default tenant to V3.

**Tasks**
- [ ] **Full eval run** vs the 150-conversation suite for V3; produce the scorecard + diff vs V2 baseline. (Owner reviews + runs manual tests — promotion is manual per D5.) → *Owner-gated: harness + command documented in [`docs/RUNBOOK-v3.md`](docs/RUNBOOK-v3.md) §4 (`python -m tests.eval.run_eval --router v3 --split all --k 3`); not auto-run (burns live tokens).*
- [x] **Concurrency + isolation hardening:** load test with two tenants in parallel; re-run cross-tenant leakage tests under the connection pooler; verify transaction-scoped GUC holds. → `tests/v3/test_concurrency_isolation.py` (40 interleaved tasks + 5-round pool churn). Green on Docker Postgres.
- [x] **Failure drills:** LLM timeout, malformed structured output, tool exception, Redis down, DB down — all fail-open to a safe Spanish message; never crash the webhook. → `tests/v3/test_failure_drills.py` (9 tests). Green.
- [x] **Runbook + rollback:** document "flip `active_router` v3→v2 in the dashboard" as instant rollback; document tenant onboarding steps. → [`docs/RUNBOOK-v3.md`](docs/RUNBOOK-v3.md).
- [x] **Docs + memory:** update `ARCHITECTURE.md`, mark V2 deprecated-but-available, update the memory index. Leave V1/V2 code in place (switchable) but freeze them.
- [ ] **Cutover:** owner flips the default tenant to V3 from the dashboard. → *Owner-gated (D5).*

**Acceptance:** V3 meets the owner's bar on the 150-set + manual tests; rollback is one dashboard toggle; isolation holds under load; docs updated.

---

## 5. Cross-cutting engineering notes

**Prompt caching (cost, D7).** OpenAI caches the longest **static prefix** automatically (up to ~90% input-token discount, no fee). So: (1) the system prompt + tool schema must be byte-identical across turns and **first**; (2) per-tenant policy next (stable within a tenant); (3) volatile state JSON **last**. Do **not** prepend per-turn context to the system prompt (V2's mistake). With Structured Outputs, drop the JSON schema text from the prompt body — the `response_format` carries it.

**Structured outputs (reliability, R1).** Use `response_format: { type: "json_schema", json_schema: {…, strict: true} }`. This guarantees parseable, schema-valid output and is the 2026 production default for extraction/agent workflows — it removes the 7-strategy `response_parser` fallback fragility.

**RLS is a safety net, not the wall.** Enforce tenant scope at **four** layers: RLS policy, DB-session GUC (`set_config(..., true)`), app ContextVar threaded into every query/tool, and automated cross-tenant tests. Never run the app as a `BYPASSRLS` role.

**Identity & sessions.** Keep BSUID-first session keying (`app/core/identity.py`, `v2_adapter` notes) but namespace by tenant: `session_id = {tenant_id}:{bsuid or phone}`. Redis keys inherit the tenant prefix.

**Eval judge caveats.** LLM judges show self-preference + score-compression bias. Keep the rubric deterministic, log raw turns for manual spot-check, and treat scores as advisory (D5).

---

## 6. Risk register

| Risk | Mitigation |
|---|---|
| Cross-tenant data leak | 4-layer enforcement + zero-leak tests in CI; transaction-scoped GUC for pooler safety |
| Backfill corrupts prod data | Alembic migration tested on a DB clone first; reversible; default-tenant backfill is idempotent |
| V3 regresses hard-won V2 behaviors | Port every `FIX/P/B` into eval cases + prompt few-shots **before** deleting the cascade |
| Cost creep on `gpt-5.4-mini` | ≤3 calls/turn budget, prompt caching verified, judge gated, embeddings = `text-embedding-3-small` |
| Structured-output refusals/empties | Hybrid fallback to regex extractors + safe clarify message; never crash |
| Render free-tier limits (DB/Redis) | Watch connection counts under RLS GUC; plan a paid tier before onboarding real tenants |
| Switch misconfig sends V3 to all tenants | `active_router` is **per-tenant**; default stays `v2` until owner flips each tenant |

---

## 7. Quick reference — "to do X, touch these"

| Goal | Files |
|---|---|
| Add the 3-way switch | `app/api/routes/webhook.py` (dispatch), `admin.py` (settings), `dashboard/src` (Config) |
| Resolve tenant from inbound | `app/api/routes/webhook.py` (`phone_number_id` → tenant), `app/db/session.py` (GUC), `app/core/identity.py` |
| The understanding pass | `app/routers/v3/{schema,engine,prompts,belief}.py` |
| Scheduling | `app/routers/v3/scheduling/fsm.py`, `app/services/appointment_service.py` |
| RAG | `app/routers/v3/knowledge/*`, pgvector migration, `property_service`/`faq_service` |
| Tenant data model | `alembic/versions/*`, `app/db/models/*` |
| Eval | `tests/eval/*`, `app/api/routes/simulate_v2.py` |

---

## 8. References (2026 research grounding)

- [Context Engineering for Production LLM Applications (2026) — Logic](https://logic.inc/resources/context-engineering-for-production-llm-applications)
- [Context Engineering Guide for AI Agents — LlamaIndex](https://www.llamaindex.ai/blog/context-engineering-what-it-is-and-techniques-to-consider)
- [Structured model outputs — OpenAI API](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Prompt caching — OpenAI API](https://developers.openai.com/api/docs/guides/prompt-caching)
- [How to architect multi-tenant SaaS on Postgres — ClickHouse](https://clickhouse.com/resources/engineering/multi-tenant-saas-postgres-architecture)
- [PostgreSQL Row-Level Security for Multi-Tenant SaaS — techbuddies.io](https://www.techbuddies.io/2026/02/04/how-to-implement-postgresql-row-level-security-for-multi-tenant-saas-2/)
- [Multi-Tenant Leakage: When RLS Fails in SaaS (pooler/CVE-2024-10976)](https://medium.com/@instatunnel/multi-tenant-leakage-when-row-level-security-fails-in-saas-da25f40c788c)
- [Multi-Turn LLM Evaluation in 2026 — Confident AI](https://www.confident-ai.com/blog/multi-turn-llm-evaluation-in-2026)
- [Rubric-Based Evals & LLM-as-a-Judge — Methodologies & Biases (2026)](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)
- [Evaluating LLM-based Agents for Multi-Turn Conversations: A Survey (arXiv 2503.22458)](https://arxiv.org/pdf/2503.22458)
- [Know Your Mistakes: Accountability Modeling for Task-Oriented Conversational AI (arXiv 2501.10316)](https://arxiv.org/pdf/2501.10316)
- [WhatsApp Business — Phone Number Management API (Meta)](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-account/phone-number-management-api)
- Internal: `router-v2-architecture-review.md`, `multi_agent_chatbot_best_practices.md`, `ARCHITECTURE.md`.

---

*Build order at a glance:* **P0** safety net → **P1** multi-tenancy → **P2** switch+skeleton → **P3** understanding engine → **P4** scheduling FSM → **P5** RAG → **P6** quality/cost → **P7** harden & cutover.
