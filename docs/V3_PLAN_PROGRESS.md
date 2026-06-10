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
| 4 | P0 | Conversation/infra | TODO | | wrap V3 webhook block in get_user_lock; consolidate belief saves (§ backlog #4) |
| 5 | P0 | Response quality | TODO | | schedule_visit fallback confirmation must emit `<!--CONFIRMED:` marker (§ backlog #5) |
| 6 | P0 | Security/infra | TODO | | verify x-hub-signature-256 against raw body bytes (§ backlog #6) |
| 7 | P1 | Response quality | TODO | | ground _synthesize_from_results in user question + history tail (§5.4) |
| 8 | P1 | Tool selection | TODO | | gate the 7b RAG safety-net when intent==search & last_search_context set (§3.2, §5.3) |
| 9 | P1 | Response quality | TODO | | concatenate multi-tool verbatim + synthesized remainder (§5.5) |
| 10 | P1 | Conversation | TODO | | persist scheduling_day/time/name to belief on engine path (§4.2) |
| 11 | P1 | Conversation | TODO | | FSM: bare `gracias` must not wipe scheduling state (§ backlog #11) |
| 12 | P1 | Conversation | TODO | | offer-acceptance few-shot: "sí" after offer → re-run search minus failed filter (§3.3) |
| 13 | P1 | Conversation | TODO | | clear stale scheduling `awaiting` on topic change (§4.3) |
| 14 | P1 | Response quality | TODO | | verbatim-aware guard: never regenerate verbatim text (§5.7) |
| 15 | P1 | Silent failure | TODO | | promote silent belief/history failures to logger.warning (§ backlog #15) |
| 16 | P1 | Booking integrity | TODO | | availability fail-open → log WARNING + metric (§ backlog #16) |
| 17 | P1 | Response quality | TODO | | cancel/reschedule: generic Spanish error, no raw exception leak (§ backlog #17) |
| 18 | P1 | Infra | TODO | | try/finally around Redis get/set to fix connection leak (§ backlog #18) |
| 19 | P2 | Persona/format | TODO | | normalize `$40.000`, fix dropped accents in no-results msg (§ backlog #19) |
| 20 | P2 | Tool selection | TODO | | resolve select_property schema/prompt drift; drop echo/get_time (§ backlog #20) |
| 21 | P2 | Conversation | TODO | | structured last_search summary lines instead of 1200-char blob (§4.4) |
| 22 | P2 | Conversation | TODO | | FSM T-7 pre-check live after #10; add unit coverage (§ backlog #22) |
| 23 | P2 | Quality | TODO | | raise RAG combine threshold to ≥0.60 (§ backlog #23) |
| 24 | P2 | Conversation | TODO | | record safety-gate turns in history (§ backlog #24) |
| 25 | P2 | Belief | TODO | | add bedrooms_match/bedrooms_max to BeliefDelta + criterios (§4.5) |

## Counts
- P0: 3/6 done · P1: 0/12 done · P2: 0/7 done · **Total: 3/25**

## In-progress notes
_(If a run stops mid-item, record here exactly what was done and what remains, so the next run resumes precisely.)_

- None yet.

## Implementation log
_(append-only; newest last — one line per completed item)_

- #1 Tool selection: surface appointment-management results verbatim before book_step guard + taxonomy line — 2026-06-10 234de0c
- #2 Response quality: requested-but-none-ran → targeted clarify (Path 0a2), never the placeholder — 2026-06-10 TBD
- #3 Conversation: reset selected_property_id + scheduling slots on new search (_apply_new_search_reset) — 2026-06-10 TBD
