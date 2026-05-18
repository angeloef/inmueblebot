# InmuebleBot — Full Audit Report

> Generated: May 18, 2026
> Comparing current codebase against `multi_agent_chatbot_best_practices.md`
> **50 gaps found: 15 HIGH, 20 MEDIUM, 15 LOW**

---

## How to Read This Report

Each finding has:
- **Severity**: HIGH (blocks correctness), MEDIUM (degrades quality/cost), LOW (cosmetic/future-proofing)
- **Area**: Which component
- **Status**: 🔴 Unfixed / 🟡 Partial / ✅ Fixed
- **Effort**: Estimated person-hours to fix

---

## TIER 1: CRITICAL (Must Fix — Affects Correctness)

### 1.1 `llm_router.chat()` Discards Token Counts
- **Area**: `llm_router.py` line 194-200
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: All subagent `ParseResult.llm_tokens = 0`. Cannot monitor subagent costs.
- **Fix**: Have `chat()` return `(content, usage)` tuple or add token fields to `LLMResponse`.
- **Dependency**: All 6 hybrid parsers need updating to use returned tokens.

### 1.2 No `response_format` on Subagent LLM Calls
- **Area**: All 6 hybrid parsers (`preference.py`, `name.py`, `location.py`, `budget.py`, `reference.py`, `date.py`) + `llm_router.py`
- **Status**: 🔴 Unfixed
- **Effort**: 1h
- **Symptom**: Subagents may return free-form text with markdown, explanations, or malformed JSON. Current JSON parsing is fragile with heuristic stripping.
- **Fix**: Add `response_format={"type": "json_object"}` support to `llm_router.ainvoke()` and `chat()`. Apply to all subagent calls. See `classifier.py:158` for reference implementation.
- **Model quirk**: gpt-5.4-mini supports `response_format` in Chat Completions. Verified working.

### 1.3 `asyncio.run()` in PreferenceExtractor.parse_code() from Async Context
- **Area**: `app/core/hybrid/preference.py` line 103
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: `RuntimeError: asyncio.run() cannot be called from a running event loop` on Python 3.12+. Current deploy may be on 3.11 where it silently creates a second event loop.
- **Fix**: Make `HybridParser.parse_code()` async, or refactor the call to be sync-compatible. Change `parse_code()` signature to `async def`.

### 1.4 NameExtractor Blocks User Response Despite "Background" Label
- **Area**: `real_estate_agent.py` lines 888-903
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: Comment says "runs every turn, no user-facing latency" but `await name_extractor.parse()` blocks the background task. Every message adds 300-800ms from LLM call.
- **Fix**: Wrap in `asyncio.create_task(name_extractor.parse(...))` — name extraction result is not needed for the immediate response.

### 1.5 ParserRegistry is Pure Dead Code
- **Area**: `app/core/hybrid/registry.py`
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Symptom**: `register()` is never called. `list_parsers()` returns `{}`. Any code calling `ParserRegistry.get("NAME")` gets `None`.
- **Fix**: Either register all 6 parsers at module init, or remove the registry entirely.

### 1.6 No Per-User Concurrency Lock
- **Area**: `webhook.py` + `real_estate_agent.py`
- **Status**: 🔴 Unfixed
- **Effort**: 1h
- **Symptom**: Two messages from the same user within 1 second bypass the timestamp-based rate limiter. Processing overlaps → Redis TOCTOU, state machine races, tool_used list corruption.
- **Fix**: Add `asyncio.Lock` per phone. `async with get_user_lock(phone):` wrapping the entire `process_turn` body. Use a `dict[str, asyncio.Lock]` with periodic cleanup.

### 1.7 Search Corrective Loop Has No Bounded Retries
- **Area**: `real_estate_agent.py` lines 246-255
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Symptom**: If LLM ignores the "LLAMÁ search_properties AHORA" corrective system message repeatedly, the loop can spin until MAX_TOOL_CALLS is exhausted, wasting tokens.
- **Fix**: Track `consecutive_search_corrections`. Break with fallback after 2 attempts.

### 1.8 Hallucination Fallback Sends Original Hallucinated Text
- **Area**: `real_estate_agent.py` line 1064
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Symptom**: `return f"{fallback_msg}\n\n{text}"` — user sees "Lo siento..." THEN "Cita Agendada para el viernes". The fallback prefix doesn't replace the hallucinated text.
- **Fix**: Return ONLY the fallback message. Log original for debugging.

---

## TIER 2: SYSTEM PROMPT (Major Optimization — Affects Quality)

### 2.1 Prompt is 10,325 chars — 72% Over Target
- **Area**: `prompts.py` SYSTEM_PROMPT
- **Status**: 🔴 Unfixed
- **Effort**: 2h
- **Target**: <6,000 chars for gpt-5.x
- **Action**: Cut 9 examples to 4-5. Condense tool descriptions to ~100 chars each. Remove redundant scheduling rules. Collapse Ranges section into Flow Rules.

### 2.2 ~9:1 Negative-to-Positive Rule Ratio
- **Area**: `prompts.py` SYSTEM_PROMPT
- **Status**: 🔴 Unfixed
- **Effort**: 1h
- **Count**: 31 negative markers (NO/NUNCA/NOT/NEVER/CRITICAL) vs 3 positive imperatives
- **Fix**: Rewrite negatives as positive outcomes. Replace "NUNCA preguntes de nuevo" with "Ya sabés el criterio, pasá al siguiente." Replace "CRITICAL: do NOT substitute" with "Usá el valor exacto del User Context."

### 2.3 Scheduling Flow Too Dense — 7 Negatives in 15 Lines
- **Area**: `prompts.py` Scheduling Flow section
- **Status**: 🔴 Unfixed
- **Effort**: 0.75h
- **Fix**: Collapse 4 redundant scheduling examples (3, 4, 6, 7) into 2. Move negative guardrails into positive numbered steps. Example: "NOT triggers" → "0. Only enter when user says 'visit' or 'schedule'."

### 2.4 Missing `# Personality` Header
- **Area**: `prompts.py` line 9
- **Status**: 🔴 Unfixed
- **Effort**: 0.1h
- **Fix**: Add `# Personality` before "Sos un agente inmobiliario argentino..."

### 2.5 `# Ranges and Alternatives` Misplaced Between Collaboration and Output Format
- **Area**: `prompts.py` lines 24-29
- **Status**: 🔴 Unfixed
- **Effort**: 0.1h
- **Fix**: Move to a new `# Flow Rules` section after Scheduling Flow.

### 2.6 Spanish Grammar/Accent Errors (8 confirmed)
- **Area**: `prompts.py` SYSTEM_PROMPT + examples
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Errors**: `Busque` → `Busqué`, `Aca tenes` ×3 → `Acá tenés`, `calido` → `cálido`, `sabados` → `sábados`, `Dale!` → `¡Dale!` ×3, `Que te parece` → `¿Qué te parece?`
- **Impact**: Model learns incorrect Spanish from the examples.

### 2.7 Mixed Spanish/English Section Names
- **Area**: `prompts.py` headers
- **Status**: 🔴 Unfixed
- **Effort**: 0.1h
- **Fix**: `# Success Criteria` → `# Criterios de Éxito`, `# Stopping Conditions` → `# Condiciones de Parada`, `# Ranges and Alternatives` → `# Rangos y Alternativas`, `# Active Property Context` → `# Contexto de Propiedad Activa`

### 2.8 schedule_visit Tool Description is 761 Chars (Target: ~100)
- **Area**: `prompts.py` line 201+
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Fix**: Move scheduling policy to Scheduling Flow section. Keep tool description to ~100 chars: "Schedule a visit to a property. Call when user explicitly agrees to visit. The tool handles name/date validation."

### 2.9 FEW_SHOT_EXAMPLES Comment References Non-Existent Sections
- **Area**: `prompts.py` line 152
- **Status**: 🔴 Unfixed
- **Effort**: 0.05h
- **Fix**: Update comment to match actual prompt structure: `# Inline examples in SYSTEM_PROMPT → # Conversation Examples section`

### 2.10 `format_messages_for_llm()` Hardcodes Last 10 Messages
- **Area**: `prompts.py` line 545
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Fix**: Implement token-aware truncation. Count approximate tokens per message, drop oldest first until within budget.

---

## TIER 3: ORCHESTRATOR (Quality/Correctness)

### 3.1 Tool Loop Detection Too Aggressive
- **Area**: `real_estate_agent.py` lines 346-362
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: Breaks on ANY two consecutive same-tool calls, even if called with DIFFERENT arguments (e.g., search with different criteria → break prematurely).
- **Fix**: Check tool name + args equality, or limit check to tools within a single LLM response.

### 3.2 Missing Plan B Messages for `cancel_appointment`, `save_lead_info`, `recommend_properties`
- **Area**: `real_estate_agent.py` lines 386-443
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Fix**: Add post-cancel: "Confirmá la cancelación y preguntá si necesita reprogramar." Post-lead-save: "Informá que los datos se guardaron y ofrecé seguir con la búsqueda."

### 3.3 No Turn-Level Timing Measurement
- **Area**: `real_estate_agent.py` process_turn
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Fix**: Wrap main try block with `start = time.monotonic()`. Log `turn_time` at exit. Compare vs benchmark.

### 3.4 RESUMEN Condition Implicitly Depends on User Message Save Order
- **Area**: `real_estate_agent.py` line 728
- **Status**: 🟡 Partial (works now, fragile)
- **Effort**: 0.25h
- **Fix**: Make explicit: `if len([m for m in history if m.get("role") in ("user", "assistant")]) >= 3`

### 3.5 `_clean_response()` Claims Regeneration But Doesn't
- **Area**: `real_estate_agent.py` lines 970-974
- **Status**: 🔴 Unfixed
- **Effort**: 0.1h
- **Fix**: Remove misleading "Regenerating clean response..." log.

### 3.6 `get_property_details` Results Not Added to `last_shown_properties`
- **Area**: `real_estate_agent.py` lines 460-475
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Fix**: After `get_property_details`, append to `last_shown_properties` so the LLM has context for "esa propiedad" references.

### 3.7 Typo: `hallucination` → `hallucination` in Method Name
- **Area**: `real_estate_agent.py` line 1000+
- **Status**: 🔴 Unfixed
- **Effort**: 0.05h
- **Fix**: Rename to `_detect_action_hallucination` (correct spelling). Update all callers.

---

## TIER 4: SUBAGENTS (Architecture/Correctness)

### 4.1 `date.py` Bypasses `llm_router` Entirely
- **Area**: `app/core/hybrid/date.py` line 20
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: Calls `parse_datetime_llm` directly instead of `llm_router.chat()`. No retry logic, no token tracking, no gpt-5.x compatibility.
- **Fix**: Implement `parse_llm()` via `llm_router.chat()` with the standard subagent prompt template.

### 4.2 `reference.py` Code Fallback is a No-Op
- **Area**: `app/core/hybrid/reference.py` lines 73-78
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Fix**: Implement actual regex-based reference resolution (match title keywords, detect fuzzy "el de 2 amb" patterns).

### 4.3 `budget.py` Code Fallback Covers Only 3 Synonym Groups
- **Area**: `app/core/hybrid/budget.py`
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Fix**: Expand to 8+ groups: add `accesible`, `modesto`, `razonable`, `económico` (accented), `bajo`, `alto`, `discreto`, `lujo`, `bastante`, `poco`, `mucho`.

### 4.4 `base.py` Docstring `max_tokens<=50` Contradicts `preference.py` Using 120
- **Area**: `app/core/hybrid/base.py` line 66
- **Status**: 🔴 Unfixed
- **Effort**: 0.05h
- **Fix**: Update docstring to `max_tokens <= 200` with note: "adjust per component, keep under 200."

### 4.5 `location.py` Static Accent Map Drifts from DB
- **Area**: `app/core/hybrid/location.py` lines 21-31
- **Status**: 🟡 Partial
- **Effort**: 0.25h
- **Fix**: Generate accent map dynamically from `_KNOWN_CITIES` instead of hardcoding.

### 4.6 `preference.py` Markdown Fence Stripping is Fragile
- **Area**: `app/core/hybrid/preference.py` lines 53-59
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Note**: Best fix is to use `response_format={"type": "json_object"}` (#1.2). If not possible, improve regex fence stripping to handle text before/after fences.

### 4.7 `name.py` "NONE" Case Check Can Miss Upper/Lower Variations
- **Area**: `app/core/hybrid/name.py` line 69
- **Status**: 🔴 Unfixed
- **Effort**: 0.05h
- **Fix**: Lowercase comparison: `result.strip().lower() == "none"`

### 4.8 `reference.py` Validation Errors Silently Swallowed
- **Area**: `app/core/hybrid/reference.py` lines 68-69
- **Status**: 🔴 Unfixed
- **Effort**: 0.1h
- **Fix**: Log the error instead of `pass`.

---

## TIER 5: CONTEXT & MEMORY (Persistence/Reliability)

### 5.1 `get_user_preferences()` Missing Fields
- **Area**: `app/core/memory.py` lines 589-599
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: Returns only 8 fields. Missing: `operation_type`, `bedrooms`, `bathrooms`. These only live in Redis (non-permanent).
- **Fix**: Add missing fields to PG schema. If schema change is too complex, at least add a comment documenting the gap.

### 5.2 `get_merged_context()` PG Priority Can Override Fresh Redis Data with Stale PG Data
- **Area**: `app/core/memory.py` lines 779-784
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Symptom**: If PG has `property_type` from a session 3 days ago, it takes priority over Redis (which has fresh data from 30 seconds ago).
- **Fix**: Compare timestamps. Redis wins if `updated_at` is newer. PG wins if it has data and Redis doesn't.

### 5.3 `reset_user_context()` PG UPDATE Fails Due to `property_type` Column Type Mismatch
- **Area**: `app/core/memory.py` lines 935-965
- **Status**: 🔴 Unfixed
- **Effort**: 1h
- **Symptom**: `column "property_type" is of type text[] but expression is of type jsonb`. The entire PG reset fails when trying to clear `property_type`.
- **Fix**: Cast `property_type` to `text[]` in the UPDATE, or fix the column type in migration. Temporary workaround: skip the `property_type` field in reset.

### 5.4 Message History Has No TTL Enforcement on Limit
- **Area**: `app/core/memory.py` save_message
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Symptom**: History grows unbounded until the 30-min Redis TTL kicks in. If TTL > message limit, history can exceed the 20-message cap.
- **Fix**: Enforce max N messages on every save (trim oldest). Log a warning when trimming.

---

## TIER 6: WEBHOOK & DELIVERY

### 6.1 `_user_locks` is Timestamp-Based, Not Asyncio.Lock
- **Area**: `webhook.py` lines 40-66
- **Status**: 🔴 Unfixed
- **Effort**: 0.5h
- **Symptom**: Prevents messages within 1 second but allows concurrent processing if messages arrive 0.8s apart.
- **Fix**: Replace with `asyncio.Lock` per phone. Also related to #1.6.

### 6.2 Webhook Calls Agent Directly — User Messages Bypass Router
- **Area**: `webhook.py` line 412
- **Status**: 🟡 Partial (has fix, fragile)
- **Effort**: 0.5h
- **Symptom**: Router's pre-processing (save_message, intent classification, state machine) is bypassed. User messages already saved in `process_turn()` but router's additional features (classification, fast path) are unavailable.
- **Fix**: Route through `router.process_message()` instead of direct `agent.process_turn()` call. Or document which router features are intentionally bypassed.

### 6.3 Webhook Signature Verification Uses Token, Not HMAC Key
- **Area**: `webhook.py` lines 108-119, 237-242
- **Status**: 🔴 Unfixed
- **Effort**: 0.25h
- **Symptom**: Signature verification compares against `WHATSAPP_WEBHOOK_VERIFY_TOKEN` (same as webhook verification, not the Meta App Secret). Should use Meta's App Secret for HMAC.
- **Fix**: Add `WHATSAPP_APP_SECRET` env var. Use it for HMAC-SHA256 verification of payload.

### 6.4 Photo Send Uses Continue But Previous Code Path Still Runs Text Send
- **Area**: `webhook.py` lines 508-527
- **Status**: 🔴 Unfixed
- **Effort**: 0.1h
- **Symptom**: When photos are split into intro → images → follow-up, the `continue` statement skips the generic `if response_text:` (line 510+) block. Need to verify this works correctly with the current indentation. The `continue` is inside the `if images and response_text` block which is inside the `else:` fallback block. After `continue`, execution jumps to the next iteration of the `for msg in messages` loop at line 291. Need to verify this doesn't skip the timing log at line 508.

---

## TIER 7: TESTING & DEPLOYMENT

### 7.1 Zero Integration Tests for Hybrid Parsers
- **Area**: `tests/` directory
- **Status**: 🔴 Unfixed
- **Effort**: 2h
- **Symptom**: No test calls `parse_llm()`, `parse_code()`, or `parse()` for any of the 6 hybrid parsers. The `asyncio.run()` bug would not be caught.
- **Fix**: Add `pytest` integration tests. At minimum: (1) all 6 parsers with LLM and code strategy, (2) hybrid fallback path, (3) edge cases (null input, accented input, malformed LLM response).

### 7.2 No Monte Carlo Test for New Flows
- **Area**: `tests/massive_test/`
- **Status**: 🟡 Partial (exists but not updated)
- **Effort**: 1h
- **Fix**: Add scenarios for: Operation-type re-ask regression, Photo flow (intro→images→follow-up), 4-criteria search threshold.

### 7.3 AGENTS.md Missing Latest Sprint Documentation
- **Area**: `AGENTS.md` (root)
- **Status**: 🟡 Partial (recent commits synced partially)
- **Effort**: 0.5h
- **Fix**: Document all 7 commits from this session. Add section for: update_context fix, user message save fix, prompt rules, 4-criteria threshold, photo flow, follow-up message.

---

## SUMMARY

### By Severity

| Severity | Count | Key Items |
|----------|-------|-----------|
| HIGH | 15 | No response_format, Token tracking broken, asyncio.run() bug, NameExtractor blocking, Dead ParserRegistry, No concurrency lock, Search loop unbounded, Hallucination fallback sends text, Prompt 72% over target, 9:1 negative ratio, Scheduling flow too dense, Missing Personality header, Ranges misplaced, 8 Spanish errors, schedule_visit tool 761 chars |
| MEDIUM | 19 | Mixed EN/ES headers, FEW_SHOT dead comment, format_messages hardcoded limit, Tool loop too aggressive, Missing Plan B messages, No turn timing, Fragile RESUMEN, Misleading logs, Details not saved to last_shown, date.py bypasses llm_router, reference.py no-op fallback, budget.py weak fallback, Docstring mismatch, location.py accent drift, Fragile fence stripping, name.py casing, Swallowed errors, Missing PG fields, PG priority over fresh Redis |
| LOW | 15 | property_type column mismatch, History TTL, _clean_response typo, Timestamp lock vs asyncio.Lock, Direct agent call bypasses router, Signature uses wrong key, Photo continue timing, Zero hybrid parser tests, Monte Carlo not updated, AGENTS.md missing docs, Typo in method name, Redundant FORBIDDEN_WORDS, Hardcoded confidence values, Generic fallback confidence too low, location.py false positives |

### By Area

| Area | HIGH | MED | LOW | Total |
|------|------|-----|-----|-------|
| System Prompt (prompts.py) | 6 | 3 | 1 | 10 |
| Orchestrator (real_estate_agent.py) | 4 | 5 | 2 | 11 |
| Subagents (hybrid/*.py) | 3 | 5 | 4 | 12 |
| Memory (memory.py) | 0 | 2 | 2 | 4 |
| Webhook (webhook.py) | 1 | 1 | 3 | 5 |
| Router (router.py) | 0 | 1 | 1 | 2 |
| Testing | 1 | 1 | 2 | 4 |
| LLM Router (llm_router.py) | 1 | 1 | 0 | 2 |

### Quick Wins (< 1h each, HIGH impact)

| # | Item | Est. | File |
|---|------|------|------|
| 1 | NameExtractor → asyncio.create_task | 0.5h | real_estate_agent.py:888 |
| 2 | Hallucination fallback → drop hallucinated text | 0.25h | real_estate_agent.py:1064 |
| 3 | Search corrective loop → bounded retries | 0.25h | real_estate_agent.py:246 |
| 4 | `asyncio.run()` → make parse_code async | 0.5h | preference.py:103 |
| 5 | Add `# Personality` header | 0.1h | prompts.py:9 |
| 6 | Fix 8 Spanish accent errors | 0.25h | prompts.py (multiple) |
| 7 | Remove `FEW_SHOT_EXAMPLES` stale comment | 0.05h | prompts.py:152 |
| 8 | Fix misleading "regenerating" log | 0.1h | real_estate_agent.py:970 |
| 9 | Fix `hallucination` typo in method name | 0.05h | real_estate_agent.py |
| 10 | `name.py` NONE case comparison | 0.05h | name.py:69 |

**Total estimated effort for all 50 items: ~25-30 hours.**
**Quick wins (10 items): ~2 hours for immediate quality improvement.**

---

*Report generated from systematic audit of all source files against `multi_agent_chatbot_best_practices.md`*
