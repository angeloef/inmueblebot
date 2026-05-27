# Merge Plan: ChatbotSerio → InmuebleBot

> **Status:** Draft v1
> **Date:** 2026-05-27
> **Goal:** Replace inmueblebot's v1.x core routing + agent logic with ChatbotSerio's v2.0 architecture, while preserving inmueblebot's production infrastructure.

---

## 0. Architecture Comparison

### What ChatbotSerio brings (the "new brain")

| Component | ChatbotSerio (v2.0) | InmuebleBot (v1.x) |
|---|---|---|
| **Router** | S1 (regex, sub-ms) → S2 (coordinator + specialists) | Intent classifier (LLM) → monolithic agent |
| **State model** | `ConversationBeliefState` — fluid dataclass, criteria accumulate across turns | `ConversationStateEnum` — rigid 15-state enum |
| **Agent** | Coordinator delegates to search/scheduling specialists with isolated tools + prompts | `RealEstateAgent` — single monolithic agent |
| **Scheduling** | Natural language: per-field responses, 5-turn escape hatch | Substate-based: SCHEDULING_ASK_DATE/TIME/CONFIRM |
| **NLP** | Empathy, formality, coherence, Argentine Spanish enrichments | None |
| **Memory** | Working + episodic + semantic + procedural + user_model (5 tiers) | Redis + PostgreSQL (2 tiers) |
| **Escalation** | Confidence-based: EXECUTE/CLARIFY_AND_EXECUTE/CLARIFY/HANDOFF | Binary: agent handles or handoff |
| **Agentic loop** | Plan → execute → evaluate → replan | Single-pass LLM call |
| **Proactive** | Proactive engine (follow-ups, re-engagement) | None |
| **Topic switching** | Conversation manager with state save/restore | Not supported |

### What InmuebleBot keeps (the "production shell")

| Component | Must preserve |
|---|---|
| **WhatsApp** | Twilio webhook (`/webhook/whatsapp`), message queue, rate limiter, dedup |
| **DB models** | `User`, `Property`, `Appointment`, `Conversation`, `Message`, `FAQ` |
| **Admin dashboard** | `/admin/*` routes, property CRUD, settings, simulation |
| **Google Calendar** | OAuth flow, event sync, calendar status |
| **Render deploy** | `render.yaml`, Dockerfile, env var structure |
| **Seed scripts** | `seed_obera.py`, `seed_faqs.py`, `seed_property_images.py` |
| **Massive test** | MCMC test framework (profiles, validators, orchestrator) |

---

## 1. Phase 1 — Foundation: File Migration & Config Merge (Day 1-2)

### 1.1 Copy ChatbotSerio files into inmueblebot

Copy these directories from `ChatbotSerio/app/` into `inmueblebot/app/`:

```
ChatbotSerio/app/routers/        → inmueblebot/app/routers/         (NEW)
ChatbotSerio/app/agents/agent.py → inmueblebot/app/agents/s2_agent.py
ChatbotSerio/app/agents/coordinator.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/agentic_loop.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/llm_client.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/conversation_manager.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/escalation.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/evaluator.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/observer.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/planner.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/thinking.py → inmueblebot/app/agents/
ChatbotSerio/app/agents/specialists/ → inmueblebot/app/agents/
ChatbotSerio/app/core/belief_state.py    → inmueblebot/app/core/
ChatbotSerio/app/core/state_transitioner.py → inmueblebot/app/core/
ChatbotSerio/app/core/context_aggregator.py → inmueblebot/app/core/
ChatbotSerio/app/core/conversation_logger.py → inmueblebot/app/core/
ChatbotSerio/app/core/response_parser.py → inmueblebot/app/core/
ChatbotSerio/app/core/metrics.py      → inmueblebot/app/core/
ChatbotSerio/app/core/proactive_engine.py → inmueblebot/app/core/
ChatbotSerio/app/core/guard_functions.py → inmueblebot/app/core/
ChatbotSerio/app/memory/              → inmueblebot/app/memory/       (NEW)
ChatbotSerio/app/nlp/                 → inmueblebot/app/nlp/          (NEW)
ChatbotSerio/app/skills/              → inmueblebot/app/skills/       (NEW)
ChatbotSerio/app/tools/ (all)         → inmueblebot/app/tools/v2/     (NEW, prefixed)
ChatbotSerio/app/api/routes/simulate.py → inmueblebot/app/api/routes/
ChatbotSerio/app/models/user_episode.py → inmueblebot/app/db/models/
ChatbotSerio/scripts/seed_data.py     → inmueblebot/scripts/
```

### 1.2 Config merge

ChatbotSerio's config is minimal (10 fields). Merge into inmueblebot's rich config:

- Add missing fields to `app/core/config.py`:
  - `INMOBILIARIA_NAME` (ChatbotSerio uses this, inmueblebot hardcodes "Inmobiliaria Oberá")
  - `S1_CONFIDENCE_THRESHOLD` (default 0.70)
  - `MAX_SCHEDULING_LOOPS` (default 5)
  - `MEMORY_TIERS`: episodic/semantic toggle
- Ensure both projects use the same `DATABASE_URL` (Render PostgreSQL)
- Verify `OPENAI_API_KEY` + `OPENAI_MODEL` are compatible

### 1.3 Dependency audit

ChatbotSerio uses:
- `openai` (async client) — already in inmueblebot
- `redis` — already in inmueblebot
- `sqlalchemy[asyncio]` — already in inmueblebot
- `pydantic-settings` — already in inmueblebot
- `loguru` — already in inmueblebot

**No new dependencies needed.**

---

## 2. Phase 2 — Core Replacement: Router + Agent (Day 3-5)

### 2.1 Replace `app/core/router.py`

**Old:** `Router.process_message()` → classifier → agent
**New:** `route_message()` from ChatbotSerio, with WhatsApp adaptation

The new flow:
```
WhatsApp webhook → extract phone/message
  → route_message(message, session_id=phone, phone=phone)
  → S1 regex match → S2 coordinator/specialist
  → return ChatResponse → send via Twilio
```

Adaptations needed:
- Map `phone` to `session_id` (currently phoned-based)
- Handle media_url (images sent via WhatsApp — pass through or store reference)
- Wire into existing rate limiter + dedup logic in `webhook.py`

### 2.2 Replace `app/agents/real_estate_agent.py`

**Old:** Monolithic `RealEstateAgent.process_turn()`
**New:** ChatbotSerio's `route_message()` is the entry point. The old `RealEstateAgent` becomes dead code.

Keep for reference during transition, delete after Phase 3 validation.

### 2.3 Replace `app/core/state_machine.py` → `app/core/belief_state.py`

**Old:** `ConversationStateEnum` with 15 rigid states + transition validation
**New:** `ConversationBeliefState` — fluid dataclass with criteria accumulation

Bridge table (for admin dashboard backward compatibility):
| Old State | Maps to Belief |
|---|---|
| `IDLE` | `active_intents` empty, `turn_count == 0` |
| `SEARCHING` | `active_intents` contains "searching" |
| `VIEWING_PROPERTY` | `selected_property_id` is not None |
| `BOOKING` | `active_intents` contains "scheduling" |
| `COMPLETED` | After schedule_visit called successfully |
| `HANDOFF` | Escalation level == HANDOFF |

**Keep** `state_machine.py` as a thin adapter that reads from `ConversationBeliefState` for admin dashboard compatibility. The admin dashboard's `GET /admin/conversation/{phone}/state` can call `belief.state_label` (a computed property).

### 2.4 Tool migration

ChatbotSerio tools are standalone async functions. InmuebleBot tools are methods on `RealEstateAgent`.

**Strategy:** Keep ChatbotSerio's tool functions as-is in `app/tools/v2/`. InmuebleBot's `app/agents/tools.py` becomes dead code.

Tool mapping:
| ChatbotSerio | InmuebleBot equivalent | Action |
|---|---|---|
| `search_properties` | `execute_search_properties` | Replace |
| `get_property_details` | `execute_get_property_details` | Replace |
| `get_property_images` | `execute_get_property_images` | Replace |
| `schedule_visit` | `execute_schedule_visit` | Replace |
| `get_faq_answer` | `execute_get_faq_answer` | Replace |
| `echo` | N/A | Keep |
| `get_time` | N/A | Keep |
| N/A | `compare_properties` | Port to ChatbotSerio |
| N/A | `cancel_appointment` | Port to ChatbotSerio |
| N/A | `reschedule_appointment` | Port to ChatbotSerio |
| N/A | `lead_capture` | Port to ChatbotSerio |
| N/A | `request_human` | Port to ChatbotSerio |

### 2.5 LLM client unification

**Old:** Three clients: `llm_router.py` (OpenAI), `llm.py` (MiniMax via OpenRouter), `gemini_client.py`
**New:** ChatbotSerio's `llm_client.py` — single OpenAI async client

Delete: `app/agents/llm.py`, `app/agents/openrouter_client.py`, `app/agents/gemini_client.py`, `app/agents/llm_router.py`

---

## 3. Phase 3 — Integration: WhatsApp + Admin + Calendar (Day 6-8)

### 3.1 WhatsApp webhook adaptation

Modify `app/api/routes/webhook.py`:

```python
# OLD
from app.agents.real_estate_agent import real_estate_agent
response = await real_estate_agent.process_turn(phone, message_text)

# NEW
from app.routers.router import route_message
response, belief, router_label, latency_ms = await route_message(
    message=message_text,
    session_id=phone,
    phone=phone,
)
response_text = response.response
```

Keep: rate limiting, dedup, WhatsApp formatting, media handling.

### 3.2 Admin dashboard compatibility

The admin dashboard (`/admin/*`) reads `ConversationStateEnum`. Create a compatibility layer:

```python
# In ConversationBeliefState, add:
@property
def state_label(self) -> str:
    """Backward-compatible state label for admin dashboard."""
    if "scheduling" in self.active_intents:
        return "booking"
    if "handoff" in self.active_intents:
        return "handoff"
    if self.selected_property_id is not None:
        return "viewing_property"
    if self.search_criteria_count >= 1 or "searching" in self.active_intents:
        return "searching"
    if self.search_criteria_count == 0 and self.turn_count > 0:
        return "qualifying"
    return "idle"
```

### 3.3 Google Calendar integration

ChatbotSerio's `schedule_visit` tool doesn't sync to Google Calendar. After a successful booking:
1. Call inmueblebot's `app/services/calendar_service.py` to create a Google Calendar event
2. Store the `event_id` in the appointment record

Add to `_update_belief_from_result()`:
```python
if "schedule_visit" in result.tools_called:
    from app.services.calendar_service import calendar_service
    await calendar_service.create_event(appointment)
```

### 3.4 Worker system

InmuebleBot uses Redis-based message queue + chat worker for async processing. ChatbotSerio is synchronous.

**Keep both paths:**
- Direct path: `route_message()` for admin simulation + testing
- Queued path: `app/workers/chat_worker.py` dequeues → calls `route_message()` → sends via WhatsApp client

---

## 4. Phase 4 — Memory & Cross-Session (Day 9-10)

### 4.1 Memory tier migration

ChatbotSerio has 5 memory tiers. InmuebleBot has 2 (Redis + PostgreSQL).

**Merge strategy:** ChatbotSerio's memory modules become the primary memory system. InmuebleBot's `memory_manager` becomes a backward-compat wrapper.

```
app/memory/
  __init__.py          ← ChatbotSerio
  working.py           ← ChatbotSerio (was app/core/belief_state.py + Redis)
  episodic.py          ← ChatbotSerio (Redis-based episode summaries)
  semantic.py          ← ChatbotSerio (structured facts from episodes)
  procedural.py         ← ChatbotSerio (tool success/failure patterns)
  user_model.py         ← ChatbotSerio (inferred persona traits)
  consolidation.py      ← ChatbotSerio (post-session summarization)
```

InmuebleBot's `app/core/memory.py` → becomes a thin compatibility layer that delegates to ChatbotSerio's memory modules.

### 4.2 Episodic memory integration

When a conversation ends (farewell or timeout):
1. `consolidate_session()` summarizes the session
2. Saves episode to Redis with `phone` as key
3. On next greeting, `build_greeting_from_episodes()` personalizes the greeting

This replaces inmueblebot's simpler `last_interaction` timestamp update.

---

## 5. Phase 5 — Testing & Validation (Day 11-13)

### 5.1 Adapt massive test framework

InmuebleBot's MCMC test framework calls `/admin/simulate`. Update to work with the new router:

```python
# tests/massive_test/orchestrator.py
# OLD: POST /admin/simulate → RealEstateAgent.process_turn
# NEW: POST /admin/simulate → route_message (S1 → S2 path)
```

Update validators in `tests/massive_test/validators.py` to check:
- Response confidence ≥ threshold
- Tools called match expected for intent
- Anti-hallucination guard passes
- Scheduling loop escapes after 5 turns

### 5.2 Run comparison tests

Before cutting over, run both old and new side-by-side on the same test inputs:

```bash
# Test 50 conversation scenarios against both old and new
python tests/compare_routers.py --scenarios 50
```

Acceptance criteria:
- New router resolves ≥ 95% of intents correctly
- Scheduling completion rate ≥ old system
- Hallucination rate ≤ old system
- Average latency ≤ old system (S1 should make it faster)

### 5.3 Admin dashboard smoke test

- Create/edit/delete properties
- View conversations, states, appointments
- Simulate conversations
- Check settings save/load
- Verify Google Calendar events appear

---

## 6. Phase 6 — Staged Rollout (Day 14-15)

### 6.1 Feature flag

Add `USE_V2_ROUTER` to bot_settings (default: `false`):

```python
# app/core/config.py
USE_V2_ROUTER: bool = False

# app/api/routes/webhook.py
if settings.USE_V2_ROUTER:
    from app.routers.router import route_message
    response, belief, _, _ = await route_message(...)
else:
    from app.agents.real_estate_agent import real_estate_agent
    response = await real_estate_agent.process_turn(...)
```

### 6.2 Rollout steps

1. **Day 14 AM:** Deploy with feature flag OFF. Smoke test old path.
2. **Day 14 PM:** Enable flag for 10% of users (phone-based bucketing). Monitor errors.
3. **Day 15 AM:** Expand to 50%. Compare conversation quality metrics.
4. **Day 15 PM:** 100% rollout. Keep old code for 1 week as rollback safety.
5. **Day 22:** Remove old code: `real_estate_agent.py`, `classifier.py`, `intent.py`, `state_machine.py`, old `tools.py`, old `prompts.py`, old LLM clients.

---

## 7. Cleanup (Day 22+)

### Files to delete after successful rollout

```
app/agents/real_estate_agent.py      (replaced by route_message)
app/agents/tools.py                  (replaced by app/tools/v2/)
app/agents/prompts.py                (replaced by specialist prompts)
app/agents/llm.py                    (MiniMax — dead)
app/agents/llm_router.py             (replaced by llm_client.py)
app/agents/openrouter_client.py      (dead)
app/agents/gemini_client.py          (dead)
app/agents/prompt_files/             (replaced by specialist prompts)
app/core/classifier.py               (replaced by S1 regex + coordinator)
app/core/intent.py                   (replaced by active_intents set)
app/core/state_machine.py            (replaced by belief_state)
app/core/hybrid/                     (replaced by state_transitioner)
app/core/memory.py                   (replaced by app/memory/)
app/core/session.py                  (replaced by working memory)
app/core/date_parser.py              (port what's still needed)
```

### Files to keep (production infrastructure)

```
app/api/routes/webhook.py            (WhatsApp — adapted to new router)
app/api/routes/admin.py              (Dashboard — kept, adapted)
app/db/                              (All models, schemas, repository — kept)
app/integrations/                    (Twilio, WhatsApp client, Calendar, Storage — kept)
app/services/                        (Appointment service, Calendar service, FAQ service — kept)
app/workers/                         (Chat worker, message queue — kept)
scripts/                             (Seed scripts — kept)
tests/massive_test/                  (MCMC framework — adapted)
```

---

## 8. Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scheduling regression (natural language vs substate) | Medium | High | Feature flag, compare scheduling completion rate |
| Admin dashboard breakage | Medium | Medium | Compatibility `state_label` property, smoke test all routes |
| Google Calendar sync failure | Low | Medium | Preserve inmueblebot's calendar service, wire into new schedule_visit |
| Memory/key loss on Redis schema change | Medium | High | Use separate key prefixes during transition (`v2:episodic:*` vs old `context:*`) |
| WhatsApp webhook breakage | Low | Critical | Keep webhook.py intact, only swap the inner call |
| LLM client auth/config mismatch | Low | Medium | Use inmueblebot's OpenAI config (already battle-tested on Render) |

---

## 9. Rollback Plan

If Phase 6 rollout shows critical issues:

1. **Immediate:** Set `USE_V2_ROUTER=false` in bot_settings. Old code path resumes instantly.
2. **Data:** ChatbotSerio memory keys use `v2:` prefix — old memory keys are untouched. No data corruption.
3. **DB:** No schema changes in Phase 1-5. Rollback is a config flip.
4. **Calendar:** New appointments created during v2 window may lack Google Calendar events. Run reconciliation script: `python scripts/reconcile_calendar.py --since 2026-06-01`.

---

## 10. Success Metrics

Measure these post-merge (compare 1 week before vs 1 week after):

| Metric | Target |
|---|---|
| Response latency (p50) | < 500ms (S1 path), < 3s (S2 path) |
| Messages handled without LLM (S1 %) | > 60% |
| Scheduling completion rate | ≥ current |
| Hallucination rate | ≤ current |
| User re-engagement (return within 7 days) | ≥ current |
| Admin dashboard functionality | 100% existing features work |

---

## Appendix: File Inventory

### ChatbotSerio files to port (~55 files)

```
app/routers/router.py              app/agents/agentic_loop.py
app/routers/system1.py             app/agents/conversation_manager.py
app/routers/system2.py             app/agents/escalation.py
app/routers/__init__.py            app/agents/evaluator.py
app/agents/agent.py                app/agents/observer.py
app/agents/coordinator.py          app/agents/planner.py
app/agents/llm_client.py           app/agents/thinking.py
app/agents/specialists/__init__.py app/core/belief_state.py
app/core/state_transitioner.py     app/core/context_aggregator.py
app/core/conversation_logger.py    app/core/response_parser.py
app/core/metrics.py                app/core/proactive_engine.py
app/core/guard_functions.py        app/nlp/*.py (4 files)
app/memory/*.py (7 files)          app/tools/*.py (8 files)
app/skills/*.py (5 files)          app/models/user_episode.py
```

### InmuebleBot files to eventually delete (~25 files)

```
app/agents/real_estate_agent.py    app/agents/tools.py
app/agents/prompts.py              app/agents/llm.py
app/agents/llm_router.py           app/agents/openrouter_client.py
app/agents/gemini_client.py        app/agents/prompt_files/*
app/core/classifier.py             app/core/intent.py
app/core/state_machine.py          app/core/hybrid/*
app/core/memory.py                 app/core/session.py
app/core/date_parser.py            app/core/graph_memory.py
```
