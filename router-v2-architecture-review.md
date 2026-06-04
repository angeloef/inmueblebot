<!-- router-v2-architecture-review.md — Architecture & intelligence review of the V2 router. Author: Hermes Agent. Date: 2026-06-04 -->
# Router V2 — Architecture Review & Intelligence Upgrade Plan

> **Scope:** End-to-end analysis of the InmuebleBot V2 routing stack (`app/routers/router.py`, `app/agents/coordinator.py`, `app/agents/s2_agent.py`, `app/core/context_aggregator.py`, `app/core/belief_state.py`, `app/agents/cs_llm_client.py`).
> **Goal:** Concrete changes that make the bot *more intelligent and make fewer mistakes*, benchmarked against current (2025–2026) frontier agent practice.
> **Date:** 2026-06-04 · **Reviewer:** Hermes Agent

---

## 0. TL;DR — The One Big Finding

The V2 router is a **well-engineered but over-grown deterministic pre-processor wrapped around an LLM**. `router.py` is **~2,960 lines** and the core `route_message` is a long chain of **~15+ ordered regex "fast-path" gates** that each intercept the turn, mutate belief state, and return *before the LLM is ever consulted*.

This design was clearly **bug-driven**: the code is littered with patch markers — `FIX 4/5`, `FIX 6`, `P1`, `P10`, `B1`–`B5`, `anti-fake-booking`, `anti-fake-reask`, `narrowing escape`, `slot-change`, `desc-disambiguate`. Each production bug spawned a new narrow regex guard whose **ordering relative to the others is load-bearing** (the comments literally say *"must run BEFORE B3"*, *"must outrank negotiator"*).

**This is the opposite of where frontier systems are going.** The 2025–2026 trend is to push linguistic understanding *into* the model via **schema-guided structured generation** and **context engineering**, keeping deterministic code for only (a) true safety gates and (b) actual side-effects (DB writes). The current architecture instead re-implements natural-language understanding in `re.compile(...)` — which is brittle, silently fails on novel phrasing, and is nearly impossible to regression-test.

**The highest-leverage move:** replace the *regex-extract → LLM-correct* pipeline and most pre-routing gates with a **single schema-guided LLM turn that returns both the updated state and the next action**, and shrink the deterministic layer to safety + side-effects. Everything else in this document supports or sequences that move.

---

## 1. What the system does today (as-built)

### 1.1 Request flow (actual, not the doc)

```
webhook → v2_adapter → route_message (session lock)
  └─ _route_message_inner:
       1.  load belief (Redis) + staleness soft-reset
       2.  /ResetMemory command
       3.  emergency regex            → human handoff (return)
       4.  human-request regex        → human handoff (return)
       5.  out-of-scope regex         → canned redirect (return)
       6.  cross-session greeting/persona build
       7.  update_belief(message)     → REGEX entity extraction into belief
       8.  build_context_prompt       → big Spanish text state block
       9.  load recent_messages (6)   → separate Redis read
       10. awaiting==show_photos      → confirm/deny/switch gate
       11. awaiting==scheduling_*     → B1..B5 sub-gates (≈400 lines)
       12. awaiting==search_narrow:*  → narrowing answer gate
       13. awaiting==disambiguate     → candidate match gate
       14. preference-ref ("la casa") → viewed-property resolver
       15. description-ref            → search-list resolver / disambiguation
       16. multi-intent photos+sched  → bespoke handler
       17. relative-cheaper           → budget *0.8 re-search
       18. FAQ question               → knowledge specialist
       19. search refinement          → deterministic belief search
       20. inmobiliaria-office visit  → location reply
       21. visit-intent               → scheduling specialist
       22. cross-turn sched persist   → scheduling specialist (+ anti-fake)
       23. _try_pre_llm_shortcut      → 6 more deterministic cases
       24. coordinate()               → LLM classify → specialist → tools → synth
  └─ route_message_with_persistence:
       25. _apply_response_guard      → LLM judge + up to 2 re-routes
       26. persist turn to Postgres
```

Steps **3–23 are deterministic regex**. The LLM only runs at **24** (and **25**'s judge). That's the inversion to keep in mind throughout.

### 1.2 The LLM layer (`coordinate` → `s2_agent`)

- **Classification:** `coordinate()` ignores the regex `classify_intent()` and calls `classify_intent_llm()` — a separate **fast-model** call (`CLASSIFY` role, `max_completion_tokens=10`).
- **Specialists:** 5 specialists (`search`, `scheduling`, `knowledge`, `rapport`, `negotiator`), each with a **filtered 1–3 tool subset** and its own system prompt. ✅ This is good practice.
- **Per specialist turn:** `process_message_with_specialist` does **REASONING call (tool decision)** → execute tools → optional **observe-retry call** → **SYNTH call (final JSON)**. So a single specialist turn is **2–3 LLM calls**.
- **Models:** `REASONING=gpt-5.5`, `CLASSIFY=SYNTH=gpt-5.4-mini` (when `LLM_TIERING_ENABLED`).

### 1.3 State

- `ConversationBeliefState` dataclass (Redis, 24 h TTL) — a fluid DST vector. ✅
- Populated by **regex extractors** in `state_transitioner.update_belief()`, then **patched** by an LLM `"correcciones"` JSON field (`_apply_belief_corrections`).

---

## 2. What's already aligned with frontier practice ✅

Credit where due — several choices are genuinely current:

| Practice | Where | Frontier alignment |
|---|---|---|
| **System-1/System-2 split** (cheap path + LLM) | `system1.py`, pre-LLM shortcuts | Cost-tiered routing; routing overhead ≪ inference cost |
| **Coordinator + specialists, 1–3 tools each** | `coordinator.py` | Directly matches the finding that tool-selection accuracy collapses past ~15–20 tools; **smaller agents with 3–5 deeply-known tools** is the recommended fix |
| **Explicit dialogue state tracking** (belief vector) | `belief_state.py` | DST is the backbone of reliable task-oriented dialogue |
| **LLM-as-judge response guard + reroute** | `_apply_response_guard` | Evaluator-optimizer / accountability modeling pattern |
| **Structured JSON output w/ schema** | `get_final_response_format` | Schema-guided generation reduces tool/format errors |
| **Hybrid parsers (code + LLM fallback)** | `app/core/hybrid/` | Graceful degradation |
| **Self-correction field** (`correcciones`) | `s2_agent` + `_apply_belief_corrections` | A reflection mechanism; self-correcting DST raises joint-goal accuracy |
| **Fail-open everywhere, per-session locks** | throughout | Solid production hygiene |
| **Deterministic booking** (don't trust LLM to assemble dates) | `specialist::sched-deterministic` | Pragmatic; side-effects stay in code |

The bones are good. The problem is **proportion**: too much intelligence lives in regex, and the LLM is boxed in rather than trusted.

---

## 3. Frontier comparison — where the gaps are

Drawing on current agent-architecture and task-oriented-dialogue work (see §7 references):

1. **Routing should be cheap and *semantic*, not a hand-ordered regex cascade.** Modern routers make a fast classification/routing decision (<50 ms) and then trust specialized executors. Here the "router" is 15+ stacked regex special-cases whose order encodes business logic. Frontier systems express routing as a small declarative policy or a single classification call.

2. **State tracking should be schema-guided and model-driven, with self-correction — not regex-first with an LLM patch.** Recent DST work shows self-correcting, schema-guided extraction reaching SOTA joint-goal accuracy (e.g. ~67→70 JGA with self-correction). The current *regex-then-correct* split means two systems fight: regex sets fields, the LLM un-sets them, and the order of operations leaks bugs.

3. **Anti-hallucination should be *structural*, not textual.** Detecting a fake booking by regex-matching Spanish phrases (`_FAKE_BOOKING`) is reactive and leaks on any phrasing the pattern misses. Frontier practice: a `booked` boolean that is *only ever* `True` because `schedule_visit` actually executed — the text layer can never assert success.

4. **Knowledge answers should be grounded (RAG).** `get_faq_answer` appears to be canned/lookup. Frontier real-estate assistants retrieve over property descriptions + policy docs and answer *with citations*, which both improves specificity and slashes hallucination.

5. **Confidence/escalation should be calibrated, not self-reported.** The LLM emits `"confianza": 0.XX` and escalation keys off it. Self-reported confidence is poorly calibrated; tool-grounded signals + the judge verdict are far more reliable triggers.

6. **Latency budget.** A single turn can fire **classify (1) → reasoning (1) → observe-retry (0–1) → synth (1) → guard judge (1) → reroute specialist (0–2 × 2 calls)** = **up to ~7 LLM calls**. Frontier single-agent function-calling collapses most of this into one tool-calling pass + one synthesis.

---

## 4. Concrete weaknesses found in the code

### 4.1 The regex cascade is unmaintainable and silently lossy
Each gate (`_is_search_refinement`, `_resolve_description_from_search`, `_REJECT_DAY`, `_NARROW_ESCAPE`, `_FAKE_BOOKING`, …) is a natural-language classifier written in `re`. Problems:
- **Ordering is load-bearing** and undocumented except in comments. Re-ordering = behavior change.
- **Silent failure**: a phrasing the regex doesn't match falls through to a *different* branch with no signal. There is no metric for "gate X misfired."
- **Spanish morphology is open-ended**: typos, voseo, slang, code-switching will always escape fixed patterns. The `difflib` fuzzy zone matcher in `_resolve_description_from_search` is evidence the team already hit this wall.

### 4.2 Dual extraction pipelines fight each other
`update_belief()` (regex) writes `operation/type/zone/budget/...`; then `_apply_belief_corrections()` (LLM) overwrites them. The whole `correcciones` mechanism exists *because* the regex layer is wrong often enough to need a model babysitter. That's a smell: if the model is correcting the regex, let the **model do the extraction** and keep regex only as the *fallback*.

### 4.3 Dead / confusing classification paths
`classify_intent()`, `_is_ambiguous_intent()`, `INTENT_PATTERNS`, `_has_clear_signal()` exist but `coordinate()` and `classify_intent_with_context()` go **straight to the LLM** (`classify_intent_llm`). The regex classifier is largely vestigial — cognitive load with little payoff.

### 4.4 Two context engines, one of them anti-pattern
`context_aggregator.py` ships a **directive engine** (good: descriptive facts) *and* a **legacy engine** full of `⚠️ NUNCA … CRÍTICO … JAMÁS` ALL-CAPS negatives — which **your own** `multi_agent_chatbot_best_practices.md` (§4.6) warns makes the bot "dumber and more timid" and prescribes a ≤1:10 negative-to-positive ratio. Keeping the legacy engine behind a flag is a latent footgun.

### 4.5 Final-text quality is gated by the *small* model
`SYNTH` (the user-facing prose) runs on `gpt-5.4-mini`, while `REASONING` runs on `gpt-5.5`. The model that *chooses* tools is smart; the model that *talks to the customer* is the mini. For a sales-funnel bot where wording drives conversion, that's backwards for the moments that matter (negotiation, objection handling, closing a visit).

### 4.6 Context block is redundant and long
`build_context_prompt` emits `[ESTADO ACTUAL]` + `[HISTORIAL DE ACCIONES]` + `[VARIABLES PENDIENTES]` + `[HISTORIAL RECIENTE]` + `[BÚSQUEDAS PREVIAS]` + last-search-context + `[OFERTA PENDIENTE]` + `[ESPERANDO RESPUESTA]` + `[ÚLTIMA PREGUNTA]`, **and** `recent_messages` is injected separately as real chat turns. Much of this overlaps (history appears 2–3 ways). For a small SYNTH model, overlapping/contradictory context is a top driver of mistakes.

### 4.7 Scheduling logic is an implicit FSM scattered across ~1,000 lines
Slot capture, proposal persistence (`_capture_proposed_slot`), availability check, anti-fake-booking, name-correction, slot-rejection, deterministic booking, loop escape — all as imperative special cases in three different places (`_maybe_confirm_or_pass`, the `awaiting` B-gates, the cross-turn persist block). The same booking can be triggered from ≥4 code paths. This is the densest bug surface in the system (and the open bug noted in `[[chatbot-optimize-loop]]`).

---

## 5. Recommendations — prioritized

> Ordered by **(intelligence gain × mistake reduction) ÷ effort**. Each is scoped so it can ship behind a flag and be A/B'd via `/admin/simulate` + the optimize loop.

### P0 — Highest leverage

**R1. Unify turn understanding into one schema-guided LLM call (structured DST + action).**
Replace `update_belief (regex) → correcciones (LLM)` with a single first-pass call that returns a typed object:
```json
{ "belief_delta": { "operation": "...", "zone": "...", ... },
  "intent": "search|scheduling|knowledge|...",
  "action": "search|show_details|book|answer_faq|clarify|handoff",
  "missing_slot": "scheduling_time|null",
  "confidence": 0.0 }
```
Keep the regex extractors **only as a fallback** when the call fails (hybrid pattern you already use elsewhere). This collapses §4.2 and most of §4.3, and is exactly the self-correcting schema-guided DST that the literature shows improves joint-goal accuracy. *Effort: M. Risk: gate behind `USE_LLM_DST` flag, shadow-run against the 150 test conversations first.*

**R2. Shrink the regex cascade to safety + side-effects only.**
Keep as deterministic gates: emergency, explicit human-request, out-of-scope, `/ResetMemory`, and the *actual* `schedule_visit` execution on explicit confirm. Route **everything else** through the coordinator, feeding it the structured belief from R1 so it has the context the gates were compensating for. Target: `route_message` from ~2,960 → **under ~600 lines**. Each deleted gate removes a silent-failure mode. *Effort: M–L. Do it gate-by-gate, each behind metrics (R8).*

**R3. Make "booked" structural, delete `_FAKE_BOOKING`.**
Surface a real signal from the tool layer: a turn is "booked" **iff** `schedule_visit` returned success. The synthesis prompt receives `booking_succeeded: true/false` and is forbidden to claim a booking otherwise. Then the ~30-line `_FAKE_BOOKING` / `_SCHED_FAILED_MARKERS` regex and the anti-fake reroutes can go. *Effort: S. Big reliability win on the worst-impact failure (fake confirmations).*

### P1 — Strong wins

**R4. Promote the customer-facing text to the strong model for high-stakes turns.**
Route `SYNTH` to `gpt-5.5` for `negotiator`, `scheduling` confirmations, and objection handling; keep `mini` for greetings/echoes. Or merge REASONING+SYNTH into one call for specialists that called ≤1 tool (the mini's separate synth pass adds latency *and* caps quality). *Effort: S.*

**R5. Collapse the LLM-call chain.**
- Fold classification into the R1 pass (no separate `classify_intent_llm`).
- Make the response guard **judge-only + one targeted regeneration** (not up to 2 full specialist reroutes). Gate the guard on `confidence < τ` or judge-flag, not on every guardable label. Target: typical turn **≤3 LLM calls** (understand → tool/answer → optional judge). *Effort: M.*

**R6. One context block, end-loaded, deduplicated.**
Kill the legacy engine (delete `USE_DIRECTIVE_ENGINE=False` path). Emit state **once** as compact JSON placed *right before* the user message (matches your own end-loading guidance for gpt-5.x). Stop injecting history three ways — pick the real `messages[]` array as the single source of conversational history; keep only *derived* facts (selected property, pending offer, awaiting slot) in the state block. *Effort: S–M.*

**R7. Ground knowledge answers with retrieval (RAG).**
Back `get_faq_answer` and property Q&A with retrieval over (a) per-property descriptions/notes and (b) a policy/FAQ corpus, and instruct the knowledge specialist to answer *only* from retrieved snippets, else say it will confirm with a human. Cuts the largest remaining hallucination surface and improves answer specificity. *Effort: M–L.*

### P2 — Reliability & insight

**R8. Instrument every router decision.**
Emit a metric per `router_label` and per regex-gate hit/miss, plus judge-verdict outcomes. You cannot safely delete a gate (R2) until you can see how often it fires and misfires. Wire into the existing `/simulate` + optimize-loop harness. *Effort: S.*

**R9. Calibrate escalation off grounded signals, not self-reported `confianza`.**
Trigger clarification/handoff from: judge verdict, repeated `consecutive_failures`, tool-error signals, and a *calibrated* threshold (measure reliability of the self-reported score on the test set first). *Effort: S–M.*

**R10. Make scheduling an explicit state machine.**
Model `idle → property_selected → day → time → name → confirm → booked` as one table-driven FSM module with a single `advance(belief, message)` entry point and a single booking call site. Replace the scattered B-gates, `_maybe_confirm_or_pass`, and cross-turn persist logic. This is where the known open bug lives — a real FSM makes it tractable. *Effort: L, but retires the densest bug surface.*

---

## 6. Suggested sequencing

| Phase | Items | Outcome |
|---|---|---|
| **1 (instrument)** | R8 | Visibility before surgery — measure gate fire/miss + misroute rate |
| **2 (de-risk facts)** | R3, R6 | Kill fake bookings; one clean context block |
| **3 (core inversion)** | R1, then R2 gate-by-gate | Model-driven understanding; cascade shrinks |
| **4 (quality/latency)** | R4, R5 | Better prose on key turns; fewer LLM calls |
| **5 (grounding)** | R7, R9 | Grounded knowledge; calibrated escalation |
| **6 (flow)** | R10 | Scheduling FSM retires the worst bug surface |

Validate every phase against the `angelo-hard-test-conversations-150.md` set + the Opus/Haiku optimize loop before promoting the flag.

---

## 7. References

Frontier practice and research consulted for this review:

- [AI Agent Routing: Tutorial & Best Practices — Patronus AI](https://www.patronus.ai/ai-agent-development/ai-agent-routing)
- [Multi-Agent Orchestration: A Practical Architecture Without the Buzzwords — Augment Code](https://www.augmentcode.com/guides/multi-agent-orchestration-architecture-guide)
- [Building Multi-Agent AI Systems: Architecture Patterns and Best Practices — DEV](https://dev.to/matt_frank_usa/building-multi-agent-ai-systems-architecture-patterns-and-best-practices-5cf)
- [From Language to Action: LLMs as Autonomous Agents and Tool Users (arXiv 2508.17281)](https://arxiv.org/pdf/2508.17281)
- [Graph-Based Self-Healing Tool Routing for Cost-Efficient LLM Agents (arXiv 2603.01548)](https://arxiv.org/pdf/2603.01548)
- [Know Your Mistakes: Preventing Overreliance on Task-Oriented Conversational AI via Accountability Modeling (arXiv 2501.10316)](https://arxiv.org/pdf/2501.10316)
- [ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use (arXiv 2408.04682)](https://arxiv.org/html/2408.04682v2)
- [Dialogue State Tracking: A Comprehensive Guide for 2025](https://www.shadecoder.com/topics/dialogue-state-tracking-a-comprehensive-guide-for-2025)
- Internal: `multi_agent_chatbot_best_practices.md` (this repo) — §4.6 negative-rule ratio, §2.2 end-loading, §6 tool guards.

---

*Companion docs in this repo: `ARCHITECTURE.md` (graph-derived map), `multi_agent_chatbot_best_practices.md` (prompt/engineering playbook), `loop-optimize-report.md` (optimize-loop findings).*
