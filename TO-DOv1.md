# TO-DO v1 — Chatbot Refactoring

## Core Philosophy

Replace the current "LLM decides everything + infinite examples" approach with:

```
Stage detection (where are we?) → Capability routing (what can we do?) →
Fail counter (should we stop?) → Handoff (graceful exit)
```

No FSM, no LangGraph, no vector DB. Keep it lightweight. ~80-100 lines of new Python.

---

## Phase 1 — Foundation: Router Layer (Priority: HIGH)

**Goal:** Create the intent routing and edge-case detection logic.

### 1.1 Create `app/agents/router.py`

New file with three functions:

- [ ] `detect_stage(message, context, history) → str`
  Heuristic classifier that returns one of the following stage tags based on conversation state flags + message keywords:
  - `SALUDO_INICIAL` — first message or new session
  - `BUSQUEDA` — user described property criteria
  - `DETALLE_PROPIEDAD` — user asking about a specific listing
  - `AGENDANDO` — `pending_scheduling` flag is set in context
  - `GESTION_TURNOS` — user mentioned reschedule/cancel
  - `CONSULTA` — FAQ about brokerage (hours, location, etc.)
  - `CONVERSACION_GENERAL` — fallback, no active flow
  - `OUT_OF_SCOPE` — detected by pattern matching
  - `HANDOFF_REQUIRED` — fail count exceeded threshold

- [ ] `detect_capability(message, context) → str | None`
  Returns which of the 6 capabilities the message maps to:
  - `"search"`, `"detail"`, `"schedule"`, `"manage_appointment"`, `"faq"`, `"contact"`
  - Returns `None` if no capability matches (→ handoff)

- [ ] `is_out_of_scope(message) → bool`
  Regex patterns for things the bot should NEVER try to handle:
  - Price negotiations ("cuánto vale", "mejor precio")
  - Legal/financial ("contrato", "impuesto", "escritura")
  - Opinions ("qué pensás", "te parece")
  - Completely off-topic (recipes, code, jokes, translations)
  - Comparisons with other brokerages

### 1.2 Add fail counter to user context

- [ ] In Redis/context manager, add `{capability}_fail_count` field
- [ ] Increment when a tool returns empty results, errors, or user rejects options
- [ ] Threshold: 2 failures per capability → trigger `HANDOFF_REQUIRED`

### 1.3 Wire router into agent flow

- [ ] Before `_build_messages()` in `real_estate_agent.py`, call `detect_stage()`
- [ ] Inject stage tag as a single line: `### ETAPA: {stage}`
- [ ] Before calling a tool, check `detect_capability()` — if `None`, trigger handoff
- [ ] After tool returns, increment fail counter if result was empty/error

---

## Phase 2 — Inject Stage Awareness (Priority: HIGH)

**Goal:** Prevent the LLM from asking "what are you looking for?" mid-flow.

### 2.1 Add stage injection to context

- [ ] In `_build_messages()`, after user context injection and before history, add:

  ```
  ### ETAPA: AGENDANDO
  ```

  This is ONE LINE. No explanation, no instructions. The LLM naturally adapts its behavior because it sees the stage tag.

### 2.2 Test key transitions

- [ ] Greeting → "SALUDO_INICIAL" → bot introduces itself
- [ ] User gives criteria → "BUSQUEDA" → bot searches, doesn't ask "what?"
- [ ] User says "quiero ver" → "DETALLE_PROPIEDAD" → bot shows details
- [ ] User agrees to visit → "AGENDANDO" → bot asks for day/time
- [ ] User says "reprogramar" → "GESTION_TURNOS" → bot fetches appointments

---

## Phase 3 — Complete Plan B Injection Gaps (Priority: HIGH)

**Goal:** Cover the 4 missing post-tool-call guidance scenarios.

### 3.1 Add pre-confirmation schedule_visit guidance

- [ ] In `real_estate_agent.py`, after `schedule_visit` returns but before `CONFIRMED`:
  - If tool asks for name → inject: "Preguntale su nombre. NO le preguntes día/horario de nuevo."
  - If tool rejects (Sunday, off-hours) → inject: "Ofrecele 2-3 alternativas. Pasá a soluciones."

### 3.2 Add cancel_appointment guidance

- [ ] Success branch → inject confirmation + "preguntale si necesita algo más"
- [ ] Failure branch → inject "informale del error, ofrecé reintentar o contactar asesor"

### 3.3 Add zero search results guidance

- [ ] After `search_properties` returns 0 results → inject alternatives message

### 3.4 Add empty FAQ guidance

- [ ] After `get_faq_answer` returns empty → inject "no tengo ese dato, ofrece ayuda con propiedades"

---

## Phase 4 — Capability Limits + Handoff (Priority: MEDIUM)

**Goal:** Stop the bot from trying to handle things it can't.

### 4.1 Define handoff trigger logic

- [ ] Handoff triggers (ANY of these):
  - `is_out_of_scope(message)` returns true
  - `detect_capability(message)` returns `None`
  - Any capability fail counter >= 2 in current conversation
  - User explicitly asks for a human ("asesor", "humano", "persona")

### 4.2 Create handoff message

- [ ] Write the handoff response text. Must:
  - Acknowledge the limitation honestly
  - Offer to transfer context so user doesn't repeat themselves
  - Sound human, not apologetic
  - Include trigger_handoff(reason) call with context summary

  ```
  "Esto escapa a lo que puedo hacer por acá. Te paso con un asesor
  humano que te va a ayudar mejor. Dejame pasarle el contexto de lo
  que veníamos hablando así no tenés que repetir todo."
  ```

### 4.3 Wire handoff into agent loop

- [ ] In main agent loop, after stage detection: if `HANDOFF_REQUIRED` or `OUT_OF_SCOPE`:
  - Call `trigger_handoff(reason=detected_reason)`
  - Send handoff message
  - End conversation turn (don't continue LLM loop)

---

## Phase 5 — Polish Few-Shot Examples (Priority: MEDIUM)

**Goal:** Strengthen existing examples, don't add new ones to cover gaps.

### 5.1 Audit existing examples

- [ ] Read current Ejemplos 1-5 in `prompts.py`
- [ ] Remove any that add ambiguity or contradict each other
- [ ] Keep only: search-results (1-result vs multi-result), scheduling, out-of-scope

### 5.2 Remove dead code

- [ ] Delete `FEW_SHOT_EXAMPLES = []` at line 143 of `prompts.py`

### 5.3 Audit for instruction duplication

- [ ] Check Plan B injection messages against prompt text for conflicts
- [ ] If a rule exists in both, keep it in ONE place (prefer injection for dynamic, prompt for static)

---

## Phase 6 — Sentiment Detection (Priority: LOW)

**Goal:** Lightweight adaptation to user mood.

### 6.1 Add keyword-based sentiment check

- [ ] Negative keywords: "no me gusta", "muy caro", "no sirve", "no me interesa"
- [ ] Urgent keywords: "urgente", "necesito ya", "lo antes posible"
- [ ] Inject sentiment tag as one line only when triggered: `### TONO: NEGATIVO`

### 6.2 Add sentiment response guidance

- [ ] In the `_build_messages()` context, when sentiment is negative:
  - No examples to add. Just the tag is enough — the LLM naturally adapts.

---

## Phase 7 — Testing & Deployment (Priority: HIGH)

### 7.1 Create test scenarios

- [ ] Flow: greeting → search → no results → user broadens → results → detail → schedule → confirm
- [ ] Flow: existing appointment → reschedule → pick new date → confirm
- [ ] Flow: user asks off-topic → detected as out-of-scope → handoff
- [ ] Flow: search fails twice → fail counter hits threshold → handoff
- [ ] Flow: user interrupts scheduling to ask FAQ → stage switches → resumes after

### 7.2 Manual testing checklist

- [ ] Stage tag is injected correctly for each phase
- [ ] Handoff triggers only on correct conditions (not false positives)
- [ ] Fail counter resets on successful capability use
- [ ] No regressions in existing flows (search, schedule, FAQ)
- [ ] Messages remain in rioplatense Spanish, warm tone

### 7.3 Deploy

- [ ] Push to main
- [ ] Monitor fail counter logs in production
- [ ] Adjust handoff thresholds based on real data after 1 week

---

## Effort Summary

| Phase | Est. Time | Files Changed | Risk |
|-------|-----------|---------------|------|
| 1. Router Layer | 1.5h | 1 new + 1 modified | Low |
| 2. Stage Awareness | 0.5h | 1 modified | Low |
| 3. Plan B Gaps | 0.5h | 1 modified | Low |
| 4. Handoff | 1h | 1 modified | Medium |
| 5. Few-Shot Polish | 0.5h | 1 modified | Low |
| 6. Sentiment | 0.5h | 1 modified | Low |
| 7. Testing | 1.5h | — | — |
| **Total** | **~6h** | **1 new + 2 modified** | |

---

## Rules of Engagement

1. **No new dependencies.** No LangChain, LangGraph, FSM libraries, vector DBs.
2. **No full rewrites.** The existing agent loop is proven. We're adding a thin layer on top.
3. **The router is NOT an LLM call.** It's regex + state flags. Cheap, fast, deterministic.
4. **Handoff is a feature, not a failure.** A bot that knows its limits is more trustworthy than one that fakes it.
5. **Stage tag is ONE LINE.** If you need more than `### ETAPA: X`, you're doing it wrong.
6. **Fail counter resets per capability per session.** Don't punish the user across conversations.
