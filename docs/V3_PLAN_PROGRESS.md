# V3 Improvement Plan — Implementation Progress

**This file is the single source of truth for what has been implemented.**
The autonomous resume task reads it first every run, picks the next `TODO` item
(P0 → P1 → P2, lowest # first), implements it, tests it, commits it, then marks
it `DONE` here with date + commit hash. Edit ONLY the status table and the log.

- Spec: [docs/V3_IMPROVEMENT_PLAN.md](V3_IMPROVEMENT_PLAN.md)
- Working branch: `v3/improvement-plan`
- Rule: **one item = one commit.** Commit (and update this file) after EACH item so
  an interrupted run never loses work.
- Commit-hash convention: commit code + tests + this file together in ONE commit, leaving
  the Commit cell as `TBD`. Do **not** `git commit --amend` to backfill the hash (it changes
  the hash and the gate blocks it). If you want the hash recorded, run a single follow-up
  `docs:` commit that fills the `TBD` cells — never amend.

## Status legend
`TODO` not started · `WIP` partially done (see notes) · `DONE` implemented + tested + committed · `BLOCKED` needs human input (see notes)

## Backlog status

| # | Pri | Area | Status | Commit | Notes |
|---|-----|------|--------|--------|-------|
| 1 | P0 | Tool selection | DONE | 234de0c | Path 0a-appt surfaces cancel/reschedule/get_my_appointments results verbatim before the book_step guard; added `scheduling → answer_knowledge` taxonomy line. 4 new tests in tests/v3/test_scheduling_guard.py. |
| 2 | P0 | Response quality | DONE | TBD | Path 0a2 in _assemble_response: tools requested but all skipped (no results) → property-scoped w/o selection asks "¿De cuál propiedad?", else _SAFE_CLARIFY_ES; never the "Un momento" placeholder. 5 tests in tests/v3/test_skipped_tool_clarify.py. |
| 3 | P0 | Conversation | DONE | TBD | _apply_new_search_reset helper: on search_properties this turn, clear selected_property_id + scheduling awaiting/day/time/pending (keep name), skip ordinal backstop. 6 tests in tests/v3/test_new_search_reset.py. |
| 4 | P0 | Conversation/infra | DONE | TBD | webhook process_messages wraps the per-user turn dispatch (v3/v2/v1) in `async with get_user_lock(phone)` — fixes the cross-message belief race. 3 offline lock tests (tests/v3/test_concurrency_lock.py). DEFERRED (intentional): (a) save-consolidation left as-is — the 3 saves are defensive checkpoints, harmless once the turn is serialized; (b) the live "2 msgs 1.2s apart → both in history" integration test needs Redis+LLM. |
| 5 | P0 | Response quality | DONE | TBD | Extracted _fallback_confirmation helper; it appends `<!--CONFIRMED:YYYY-MM-DD HH:MM-->` (from parsed start_datetime) so a real booking with no appointment object is treated as success, not discarded. 5 tests in tests/v3/test_fallback_confirmation_marker.py. |
| 6 | P0 | Security/infra | DONE | bd85a9f | receive_webhook reads raw body bytes, verifies HMAC-SHA256 x-hub-signature-256 against new WHATSAPP_APP_SECRET; fail-closed 403 when secret set + bad/missing sig, skip when unset (legacy). verify_webhook_signature rewritten bytes-based. 8 tests in tests/v3/test_webhook_signature.py. |
| 7 | P1 | Response quality | DONE | TBD | _synthesize_from_results now takes user_message; prompt carries "Pregunta del usuario" + recent history tail (new _recent_history_tail helper drops the trailing current-user line) so LLM Call 2 answers the asked question, not a generic FAQ. user_message threaded through _assemble_response. 7 tests in tests/v3/test_synthesis_grounding.py. |
| 8 | P1 | Tool selection | DONE | TBD | New _is_about_shown_results(turn, belief) predicate gates Step 7b: when intent==search & last_search_context set, the RAG safety-net is skipped so a "¿cuál es la más barata?" follow-up answers from ultima_busqueda, not injected FAQ chunks. Prompt §3.2 applied: knowledge taxonomy scoped to "proceso inmobiliario"; "sobre lo ya mostrado" few-shot rewritten to intent:search/action:clarify/tool_calls:[]. 4 tests in tests/v3/test_rag_safetynet_gate.py. |
| 9 | P1 | Response quality | DONE | TBD | Path 0b2 now keeps the specificity-ordered verbatim block (detail > list) AND appends a synthesized tail from remaining non-verbatim _DATA_TOOLS (e.g. get_faq_answer) so a multi-intent "busco depto + ¿qué requisitos?" returns both list and requisitos. Errored remainders skipped; single-verbatim turns unchanged (no extra LLM call). 4 tests in tests/v3/test_multi_tool_concat.py. |
| 10 | P1 | Conversation | DONE | TBD | Two persistence points: _execute_tools calls _persist_schedule_args on schedule_visit (copies dia/horario/nombre, never wipes on partial re-emit); run_turn step 6 calls _persist_scheduling_slots_from_message (scheduling turns only → real day/time extractors → belief.scheduling_*, never clears on miss). Slots now survive the history window + revive FSM T-7. 7 tests in tests/v3/test_scheduling_slot_persist.py. |
| 11 | P1 | Conversation | DONE | TBD | FSM: removed bare `gracias` from _EXIT_CUES; added _THANKS_ONLY_RE (anchored ^…$) so "gracias" ends the flow only as a standalone thank-you. "sí, gracias, soy Juan" at NEED_NAME now preserves day/time/awaiting; strong cues (chau/no gracias/busco otra) still exit. 7 tests in tests/v3/test_gracias_midflow.py. |
| 12 | P1 | Conversation | DONE | TBD | Prompt-only (§3.3): added "Aceptación de una oferta del sistema" few-shot — affirmation after a search fallback offer ("sí, dale") → intent:search/action:search re-running search_properties minus the failed filter, not smalltalk. R4 negative ratio re-verified under cap. 3 tests in tests/v3/test_offer_acceptance_prompt.py. |
| 13 | P1 | Conversation | DONE | TBD | New _clear_stale_scheduling_awaiting(belief, turn, prev_last_intent) in step 6: clears awaiting + pending_scheduling only when this turn AND the previous one are both non-scheduling and awaiting still startswith "scheduling_". prev_last_intent captured before last_intent overwrite. Single FAQ interruption (prev was scheduling) preserves the flow; scheduling_name untouched. 6 tests in tests/v3/test_stale_awaiting_clear.py. |
| 14 | P1 | Response quality | DONE | TBD | _assemble_response now returns a 3rd value source ∈ {verbatim,synthesis,plan,fsm}; threaded into run_guard(source=...). When source=="verbatim" the judge still SCORES but never regenerates — deterministic search list / detail card / real confirmation reach the user byte-exact (no LLM price/format drift). Updated all 18 returns + run_turn caller + 5 test files' unpacking. 2 new tests in test_quality_guard.py (verbatim not-regenerated + synthesis control). |
| 15 | P1 | Silent failure | DONE | TBD | belief.py: added loguru logger; load_belief_v5 deserialize/migrate failure + outer except now log WARNING (were `except: pass`); save_belief_v5 except logs WARNING. engine.py step 8c assistant-history append promoted debug→warning. All still non-fatal (graceful fresh belief / turn proceeds). 2 tests in tests/v3/test_silent_failure_logging.py (loguru sink capture). |
| 16 | P1 | Booking integrity | DONE | TBD | New emit_availability_failopen(stage, property_id, reason) in turn_metrics.py logs a selectable AVAILABILITY_FAILOPEN marker line (WARNING). Wired into both fail-open branches of appointment_service.check_slot_availability (calendar sub-check + outer DB check). Fail-open behavior preserved (product call); now observable for rate alerting. 4 tests in tests/v3/test_availability_failopen.py. |
| 17 | P1 | Response quality | DONE | TBD | cancel_appointment / reschedule_appointment except blocks no longer interpolate the raw exception into the user reply ("No pude cancelar la visita: {e}" leaked asyncpg/SQL text). Now a generic Spanish retry message; detail stays in logger.error. 2 tests in tests/v3/test_appt_error_no_leak.py assert the sentinel/asyncpg text never reaches the user. |
| 18 | P1 | Infra | DONE | TBD | load_belief_v5 + save_belief_v5 wrap the redis get/set in try/finally so aclose() always runs (was happy-path only → one leaked connection per error). 3 tests in tests/v3/test_redis_no_leak.py (fake redis raising in get/set asserts aclose still awaited + turn degrades). |
| 19 | P2 | Persona/format | DONE | TBD | get_faq_answer curated "precios" fallback: comma-thousands → dot-thousands ($40,000→$40.000, …$22.000.000). search_properties no-results msg accents fixed ("No encontré propiedades… ¿Querés ajustar algún filtro?"). Legacy V1/V2 prompt strings left as-is (out of V3 scope). 3 tests in tests/v3/test_format_normalization.py. |
| 20 | P2 | Tool selection | DONE | TBD | Dropped echo/get_time from _TOOL_NAMES + their prompt tool-list lines (no real-estate purpose, invited off-task calls; still in registry for legacy). Removed dead select_property from the action enum (never in taxonomy nor engine-handled). 5 tests in tests/v3/test_schema_prompt_consistency.py incl. "every action enum value appears in the prompt taxonomy". |
| 21 | P2 | Conversation | DONE | TBD | _persist_search_context now stores _compact_search_summary(res): one "ID:N — Tipo en Zona — $precio" line per property (whole, never char-truncated), spec/prose lines dropped, capped at _MAX_SUMMARY_LINES=12. Falls back to res[:1200] for non-list messages (no-results/progressive-narrowing). Cheaper tokens + clean comparative material. 6 tests in tests/v3/test_compact_search_summary.py. |
| 22 | P2 | Conversation | DONE | TBD | T-7 availability pre-check is live now that #10 persists scheduling_day/time. Test-only item: 3 tests in tests/v3/test_fsm_availability_precheck.py — taken slot → override + re-ask time (scheduling_time cleared, awaiting=scheduling_time), free slot → no override (slot untouched), already-booked → check skipped. No production change. |
| 23 | P2 | Quality | TODO | | raise RAG combine threshold to ≥0.60 (§ backlog #23) |
| 24 | P2 | Conversation | TODO | | record safety-gate turns in history (§ backlog #24) |
| 25 | P2 | Belief | TODO | | add bedrooms_match/bedrooms_max to BeliefDelta + criterios (§4.5) |

## Counts
- P0: 6/6 done · P1: 12/12 done · P2: 4/7 done · **Total: 22/25** ✅ all P0+P1 complete

## In-progress notes
_(If a run stops mid-item, record here exactly what was done and what remains, so the next run resumes precisely.)_

- None yet.

## Implementation log
_(append-only; newest last — one line per completed item)_

- #1 Tool selection: surface appointment-management results verbatim before book_step guard + taxonomy line — 2026-06-10 234de0c
- #2 Response quality: requested-but-none-ran → targeted clarify (Path 0a2), never the placeholder — 2026-06-10 TBD
- #3 Conversation: reset selected_property_id + scheduling slots on new search (_apply_new_search_reset) — 2026-06-10 TBD
- #4 Conversation/infra: serialize per-user webhook dispatch with get_user_lock — 2026-06-10 TBD
- #5 Response quality: schedule_visit fallback confirmation emits CONFIRMED marker (_fallback_confirmation) — 2026-06-10 TBD
- #6 Security/infra: verify x-hub-signature-256 over raw body (WHATSAPP_APP_SECRET, fail-closed 403) — 2026-06-10 bd85a9f
- #7 Response quality: ground synthesis (LLM Call 2) in user question + recent history tail — 2026-06-10 TBD
- #8 Tool selection: gate Step 7b RAG safety-net on answer-about-shown-results + prompt §3.2 — 2026-06-10 TBD
- #9 Response quality: concatenate verbatim block + synthesized remainder for multi-intent turns — 2026-06-10 TBD
- #10 Conversation: persist scheduling day/time/name to belief on the engine path — 2026-06-10 TBD
- #11 Conversation: bare `gracias` no longer wipes scheduling state (thanks-only exit) — 2026-06-10 TBD
- #12 Conversation: offer-acceptance few-shot — "sí" after offer re-runs search minus failed filter — 2026-06-10 TBD
- #13 Conversation: clear stale scheduling awaiting after two consecutive off-topic turns — 2026-06-10 TBD
- #14 Response quality: verbatim-aware guard (source flag) never regenerates verbatim text — 2026-06-10 TBD
- #15 Silent failure: promote belief load/save + assistant-history failures to logger.warning — 2026-06-10 TBD
- #16 Booking integrity: availability fail-open emits AVAILABILITY_FAILOPEN metric line — 2026-06-10 TBD
- #17 Response quality: cancel/reschedule return generic Spanish error, no raw exception leak — 2026-06-10 TBD
- #18 Infra: try/finally around Redis get/set so aclose() always runs (no connection leak) — 2026-06-10 TBD
- #19 Persona/format: dot-thousands in curated FAQ prices + accents in no-results msg — 2026-06-10 TBD
- #20 Tool selection: drop echo/get_time from V3 enum + remove dead select_property action — 2026-06-10 TBD
- #21 Conversation: compact per-ID search summary lines instead of 1200-char blob — 2026-06-10 TBD
- #22 Conversation: unit coverage for live FSM T-7 availability pre-check (post-#10) — 2026-06-10 TBD
