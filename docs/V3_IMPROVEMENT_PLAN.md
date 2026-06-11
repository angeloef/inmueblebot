# V3 Engine — Quality, Tool-Selection & Conversation Improvement Plan

Date: 2026-06-10 · Scope: `app/routers/v3/` + `app/tools/v2/` (read-only analysis, no code changed)
Inputs: manual file audit + silent-failure-hunter + fastapi-reviewer agent reports.

---

## 1. Architecture execution map

### Path A — Search query (webhook → WhatsApp send)

```
webhook POST /webhook  (asyncio.ensure_future, fire-and-forget, returns 200 immediately)
 └─ process_messages → _resolve_active_router → process_turn_v3 (adapter.py)
     ├─ set_current_contact / set_current_tenant (ContextVar)
     └─ run_turn (engine.py)
         Step 1  load_belief_v5(session_id)            [STATE READ — Redis; silent fresh-belief on ANY failure]
         Step 2  regex safety gates (emergency / human / out-of-scope / reset)  [0 LLM]
                 ⚠ gate paths return WITHOUT appending the user msg to history → context hole
         Step 3  build_messages(system + tenant_policy + history + user + [ESTADO])
         Step 4  LLM CALL 1 — gpt-5.4-mini, strict json_schema TURN_JSON_SCHEMA,
                 max 1024 completion tokens; prompt ≈ 2.3k tokens system + ~0.15k policy
                 + history (≤8 entries) + state JSON
         Step 5  _apply_fallback (regex hybrid if delta all-null; full regex turn if call failed)
         Step 6  apply_belief_delta → turn_count/history/last_action/selected_property_id/awaiting
                 [STATE WRITE 1 — save_belief_v5]
         Step 7  _execute_tools → search_properties(...)
                 ⚠ invalid args → tool silently SKIPPED (debug log only)
                 → _persist_search_context (last_search_ids / count / context[:1200])
         Step 7c FSM resolve (no-op for search)        [STATE WRITE 2]
         Step 8  _assemble_response:
                 Path 0b2 → search_properties result rendered VERBATIM  ✅
                 ⚠ if engine ALSO called get_faq_answer this turn, that result is DROPPED (first-wins)
         Step 8b guard.run_guard — judge fires only if conf<0.70 or action critical
                 ⚠ a low-confidence search turn can REGENERATE the verbatim list via LLM
                   (re-introducing price/format drift the verbatim path was built to prevent)
         Step 8c append "assistant: …" to history       [STATE WRITE 3 — debug-only log on failure]
 └─ webhook: response_plan segments sent in order (text → images[≤4] → text), else single text
```

**Silent-failure hotspots:** belief load (fresh state, no log) · tool validation skip → engine placeholder `"Un momento, reviso eso."` becomes the final reply (dead end) · 3 racing belief saves with **no per-user lock** anywhere in the webhook→V3 path.

### Path B — Booking flow

```
turn N..N+k  intent:scheduling, action:clarify, missing_slot=… → belief.awaiting set
             ⚠ scheduling_day/time/name are NEVER written to belief on the engine path
               (only the regex full-fallback writes them) → slot values live ONLY in
               history (HISTORY_WINDOW=8 entries = ~4 exchanges since assistant msgs count)
turn N+k+1   action:book_step + tool_calls:[schedule_visit{property_id,dia,horario,nombre}]
             property_id backfilled from belief.selected_property_id if omitted
             ⚠ selected_property_id is never reset on a new search → can backfill a STALE id
 schedule_visit tool:
   require property_id/dia/horario → weekday-vs-date cross-check → hybrid date parse
   → past-date roll-forward (informed) → business-hours gate (fail-CLOSED ✅)
   → availability check (fail-OPEN ⚠ double-booking under DB errors)
   → plausible-name gate → user resolve by session identity → create_appointment
   → success: format_appointment_confirmation emits <!--CONFIRMED:…--> marker
   ⚠ the no-appointment-object fallback confirmation (lines 296-319) does NOT emit the
     marker → booking_succeeded=False → Path 0b discards it → real booking, user told
     "estoy recopilando los detalles" (H-4)
 FSM resolve: T-1 booked cleanup · T-2 exit cues (⚠ "gracias" wipes scheduling state)
   · T-6 loop counter (→ handoff after 3) · T-7 availability pre-check (mostly DEAD code:
   it reads scheduling_day/time which the engine path never populates)
 Assembly: book_step + marker → surface REAL confirmation ✅
           book_step w/o marker → surface schedule_visit's re-ask/rejection ✅
           ⚠ action==book_step with cancel/reschedule tools (no schedule_visit) →
             results DISCARDED, user gets "estoy recopilando los detalles para tu visita"
```

### Path C — FAQ / knowledge query

```
action:answer_knowledge
 ├─ engine emitted get_faq_answer → tool runs:
 │    pgvector search_knowledge (threshold .50, top-k) → ≥.75 sim: chunk verbatim;
 │    else combine 2 chunks → keyword DB fallback → curated Oberá fallback (default tenant
 │    only; ⚠ comma-formatted prices "$40,000" violate the dot-thousands rule) → safe deferral
 └─ engine emitted NO tool → Step 7b RAG safety-net injects top-3 chunks as
    "knowledge_retrieval" ⚠ fires even when the question is about the JUST-SHOWN search
    results ("¿cuál tiene más ambientes?") because the prompt few-shot says
    answer_knowledge w/o tools for that case while the taxonomy says "SIEMPRE get_faq_answer"
 Assembly: must_surface → LLM CALL 2 _synthesize_from_results
    ⚠ synthesis prompt contains tool results + [ESTADO] but NOT the user's question and
      NOT the history → answer can be unfocused / answer the wrong question
 Guard: answer_knowledge is a CRITICAL_ACTION → judge always fires (LLM CALL 3)
```

### Path D — Out-of-hours rejection

```
schedule_visit step 3: load_tenant_hours (FAQ "horario" parse → Tenant.business_hours →
defaults Mon-Fri 9-18 / Sat 9-13) → tenant-tz localization → weekday-not-in-windows or
hour-out-of-window → returns informed rejection with describe_hours(...)
booking_succeeded=False → Path 0b surfaces the rejection text verbatim ✅
FSM: missing_slot loop counter eventually escalates to handoff ✅
Hotspot: hours gate fail-closed ✅; but the FSM pre-check (T-7) that should reject the slot
BEFORE the tool runs is dead because belief scheduling slots are unpopulated (see §4).
```

---

## 2. Prioritized improvement backlog

| # | Pri | Area | Finding | Root cause | Proposed fix | Test to validate |
|---|-----|------|---------|------------|--------------|------------------|
| 1 | **P0** | Tool selection | `cancel_appointment` / `reschedule_appointment` / `get_my_appointments` succeed but user gets *"Estoy recopilando los detalles para tu visita"* when the model labels the turn `book_step` | Path 0b guard keys on `action=="book_step"` alone, not on whether `schedule_visit` was actually requested; taxonomy has no action for appointment management | Guard condition → `action=="book_step" and "schedule_visit" in requested`; add prompt taxonomy line for appointment management (§3.1) | Eval: "cancelá mi visita del jueves" → expect `cancel_appointment` + its confirmation text |
| 2 | **P0** | Response quality | All requested tools skipped by validation → engine's ≤8-word placeholder ("Un momento, reviso eso.") is the final reply; conversation dead-ends | `_execute_tools` skips invalid calls with a debug log; Path 1 then renders the placeholder `response_plan` verbatim | After tool loop: `if turn.tool_calls and not any_ran` → emit targeted clarify (e.g. missing `property_id` → "¿De cuál propiedad…?"), never the placeholder | Eval: "mostrame los detalles" with empty belief (no selection, no search) → expect a question, not a placeholder |
| 3 | **P0** | Conversation | Stale `selected_property_id` survives a new search → "mostrame fotos" backfills the OLD property; user can book/see the wrong unit | No reset-on-new-search in `apply_belief_delta`/engine step 6; `_PROPERTY_ID_TOOLS` backfill trusts the stale value | When `search_properties` is requested this turn → clear `selected_property_id`, `awaiting`, scheduling day/time (keep name) before tool exec (§4.1) | Eval: select ID:7 → new search → "mostrame fotos" → expect clarify or a property from the NEW list, never ID:7 |
| 4 | **P0** | Conversation/infra | Two rapid messages from the same user run concurrent turns; 3 belief saves per turn race and last-writer-wins (slots/history silently lost) | Webhook never wraps V3 in the existing `get_user_lock()` (V1 does); engine saves at steps 6, 7c, 8c | `async with get_user_lock(phone):` around the per-message block in `process_messages`; consolidate to one save after step 8c | Integration: send 2 msgs 1.2 s apart; assert both turns appear in history |
| 5 | **P0** | Response quality | Real booking created but user gets no confirmation when service returns `success` without an appointment object | Fallback confirmation block in `schedule_visit` (≈ lines 296-319) lacks the `<!--CONFIRMED:` marker → `booking_succeeded=False` → Path 0b discards it | Append the marker to the fallback confirmation (and use parsed `start_datetime`, not raw `dia/horario`) | Unit: mock `create_appointment` → `{"success": True}` no object → assert confirmation text reaches user and FSM resets |
| 6 | **P0** | Security/infra | Webhook signature verification skipped unconditionally — anyone with the URL can forge user turns | `verify_webhook_signature` never called; would also fail (str vs raw bytes) | Verify `x-hub-signature-256` against `await request.body()` raw bytes | Unit: forged payload → 403 |
| 7 | **P1** | Response quality | Synthesis (LLM Call 2) answers without seeing the user's question or history → unfocused/wrong-topic FAQ answers | `_synthesize_from_results` builds messages from tool results + state only | Add `user_message` (and last 2 history turns) to the synthesis user prompt | Eval: "¿aceptan mascotas en el depto del centro?" → answer addresses pets, not generic FAQ dump |
| 8 | **P1** | Tool selection | Questions about JUST-SHOWN results ("¿cuál es la más barata?") get routed to RAG → irrelevant FAQ/property chunks synthesized instead of answering from `ultima_busqueda` | Prompt contradiction: taxonomy says answer_knowledge ⇒ ALWAYS `get_faq_answer`; few-shot (line 132) says answer_knowledge with `tool_calls:[]`; Step 7b RAG safety-net then injects chunks | Skip the 7b safety-net when `belief.last_search_context` is set and intent==search; fix the prompt contradiction (§3.2) | Eval: list shown → "¿cuál tiene más ambientes?" → expect no `get_faq_answer`/RAG, answer cites IDs from the list |
| 9 | **P1** | Response quality | Multi-intent turn (search + FAQ in one message) loses the second tool's data | Path 0b2 verbatim render is first-wins; returns after the first verbatim tool | Concatenate: verbatim block + synthesized remainder (`"\n\n"`-joined) | Eval: "busco depto en centro, ¿y qué requisitos piden?" → both list and requisitos present |
| 10 | **P1** | Conversation | Booking slots given early are forgotten in long flows (re-ask loops) — engine path never persists day/time/name to belief; history holds only ~4 exchanges | Belief writes for `scheduling_*` exist only in the regex fallback; HISTORY_WINDOW=8 entries now includes assistant msgs | Persist `schedule_visit` args + per-turn slot answers into `belief.scheduling_*` (§4.2); consider HISTORY_WINDOW 8→12 | Eval: 7-turn booking with a FAQ interruption → day given at turn 2 still used at turn 7 |
| 11 | **P1** | Conversation | "sí, gracias, soy Juan" (or any polite *gracias*) mid-scheduling wipes day/time/name | FSM `_EXIT_CUES` includes bare `gracias` | Require standalone exit ("no gracias", "chau") or `gracias` as the whole message; never wipe when the same msg contains a name/slot token | Unit (FSM): msg "sí, gracias, soy Juan" at NEED_NAME → state preserved, name captured |
| 12 | **P1** | Conversation | "sí" after the tool's offer "¿Querés que te las muestre?" has no deterministic handling → likely smalltalk misroute | Offer questions from search fallbacks aren't represented in belief (`pending_offer` unused in V3); no few-shot | Few-shot (§3.3): affirmation after an offer in `ultima_busqueda` ⇒ re-run `search_properties` minus the failed filter | Eval: zone-miss → offer → "sí" → expect search_properties without zona |
| 13 | **P1** | Conversation | `awaiting` stuck at `scheduling_*` after the user abandons booking → `[ESTADO]` keeps telling the LLM it's waiting for a slot | Cleared only on book_step-with-no-missing-slot or FSM exit/loop paths | Engine step 6: if `turn.intent != "scheduling"` and `awaiting` is a scheduling slot for >1 turn → clear it (or FSM T-3 clears after N off-topic turns) | Eval: start booking → "mejor mostrame casas en venta" → next [ESTADO] has no `esperando` |
| 14 | **P1** | Response quality | Judge regeneration (LLM Call 3) can rewrite VERBATIM deterministic outputs (search list, detail card) on low-confidence turns → format drift returns | `run_guard` doesn't know the text came from the verbatim path | Pass `source="verbatim"` flag; judge may score but never regenerate verbatim text | Unit: conf=0.5 + verbatim list → assert response identical pre/post guard |
| 15 | **P1** | Silent failure | Belief load failure silently starts a fresh conversation (no log); assistant-history save failure logged at DEBUG | `except Exception: pass` in `load_belief_v5`; debug-level log at step 8c | Promote both to `logger.warning` (+ all agent findings H-5..H-8, M-3) | Log assertion tests |
| 16 | **P1** | Booking integrity | Availability check fail-OPEN twice (tool step 3b + availability.py) → double-booking when DB errors | Deliberate fail-open, but logged at debug only | Keep fail-open (product call) but log WARNING + emit metric; consider fail-closed for repeated failures | Unit: raise in `check_slot_availability` → warning logged |
| 17 | **P1** | Response quality | Cancel/reschedule leak raw exception text to the user (`No pude cancelar la visita: {e}`) | Broad `except` interpolates the exception | Generic Spanish message + `logger.error` (agent C-2/C-3) | Unit: forced FK error → no `asyncpg` text in reply |
| 18 | **P1** | Infra | Redis connection leaked on exception in every belief load/save | `aclose()` only on happy path | `try/finally` around get/set | — |
| 19 | **P2** | Persona/format | Curated FAQ fallback uses `$40,000` (commas) + hardcoded Oberá contact; `search_properties` no-results msg drops accents ("No encontre… Queres") | Legacy strings predating the format rules | Normalize to `$40.000`, fix accents | Eval format assertions (§6) |
| 20 | **P2** | Tool selection | `select_property` action exists in schema enum but is never defined in the prompt taxonomy; `echo`/`get_time` reachable by the model | Schema/prompt drift | Document or remove from enum; drop echo/get_time from `_TOOL_NAMES` | Schema/prompt consistency unit test |
| 21 | **P2** | Conversation | `last_search_context` capped at 1200 chars → descriptive selection ("la de Schuster") can reference a truncated entry | Cap protects state JSON size | Store a compact per-ID summary line (id, tipo, zona, precio) instead of the raw blob prefix | Eval: 7-result list, pick by zone name of last item |
| 22 | **P2** | Conversation | FSM T-7 availability pre-check + CONFIRM state are dead code on the V3 path | Depends on `scheduling_*` belief fields the engine never writes (fixes with #10) | After #10, T-7 becomes live; add unit coverage | FSM unit: CONFIRM + taken slot → suggestions |
| 23 | **P2** | Quality | RAG threshold 0.50 admits weakly-related chunks into answers (combined-2 path) | Low default threshold | Raise combine path to ≥0.60 or only combine chunks within 0.1 of top | Eval: obscure question → safe deferral, not loose chunk |
| 24 | **P2** | Conversation | Safety-gate turns (emergency/human/OOS) never recorded in history → the next engine turn can't see them | Gates return before history bookkeeping | Append `user:`/`assistant:` entries before returning from gates | Eval: OOS joke → "ok, busco depto" → no re-greeting confusion |
| 25 | **P2** | Belief | `bedrooms_match`/`dormitorios_max` live only in tool args → later refinements silently revert to `exact` | Belief delta schema lacks them | Add to BeliefDelta + apply_belief_delta (and to `criterios` state) | Eval: "2 a 3 dormitorios" → "y en el centro?" → re-search keeps range |

---

## 3. Prompt improvements (surgical diffs to `prompts.py`)

### 3.1 Appointment-management taxonomy line (fixes backlog #1 with the code guard)

```diff
 scheduling → book_step (ya hay property_id + día + horario + nombre → emití schedule_visit ESTE turno)
 scheduling → clarify (falta día, horario o nombre → pedí solo ese, sin tool_call)
+scheduling → answer_knowledge (gestionar visitas YA agendadas: listar → get_my_appointments;
+             cancelar → cancel_appointment; cambiar día/hora → reschedule_appointment.
+             book_step es SOLO para crear una visita nueva con schedule_visit.)
```

Rationale: today the model has no labeled path for cancel/reschedule, so it gravitates to `book_step` and trips the anti-hallucination guard. `answer_knowledge` is already a must-surface data path, so results render correctly.

### 3.2 Resolve the answer-from-results contradiction (fixes #8)

```diff
-knowledge  → answer_knowledge (FAQ inmobiliaria — SIEMPRE llamar get_faq_answer; nunca inventar)
+knowledge  → answer_knowledge (FAQ del PROCESO inmobiliario — requisitos, garantía, contrato,
+             mascotas, zonas, contacto → SIEMPRE llamar get_faq_answer; nunca inventar)
```

```diff
-Sin loop tras resultados (pregunta sobre lo ya mostrado → respondé del estado, sin re-buscar):
-usuario: "cuál tiene más ambientes?" → action:answer_knowledge/clarify usando el estado, tool_calls:[]
+Pregunta sobre los resultados YA mostrados (comparativas, precios de la lista) → respondé desde
+ultima_busqueda del estado, SIN herramientas:
+usuario: "¿cuál tiene más ambientes?"
+BUENO → intent:search, action:clarify, tool_calls:[], response_plan:[{type:text, content:
+"De la lista, el Departamento ID:12 en Centro es el de más ambientes (3 dormitorios). ¿Querés ver los detalles?"}]
+MALO → action:answer_knowledge con get_faq_answer (eso es para requisitos/garantías/contrato,
+no para comparar la lista).
```

Pair with the engine change: never fire the 7b RAG safety-net when `intent=="search"` (§5.3). Note: `clarify` is reused here as the "respond-from-state" action to avoid a schema change; if you accept a one-line schema edit, adding `answer_results` to the action enum is cleaner and lets the engine assert `tool_calls==[]` for it.

### 3.3 Offer-acceptance few-shot (fixes #12)

```diff
+Aceptación de una oferta del sistema (el último mensaje ofreció mostrar opciones):
+estado: {ultima_busqueda:"No tenemos departamentos en la zona de Villa Bonita. Sí tengo 4
+departamentos en otras zonas. ¿Querés que te las muestre?"}
+usuario: "sí, dale"
+BUENO → intent:search, action:search, tool_calls:[{name:search_properties,
+arguments:{"operation":"alquiler","tipo":"departamento"}}]  (mismos criterios SIN la zona que falló)
+MALO → action:smalltalk con "¡Genial!" y tool_calls:[] (deja al usuario esperando).
```

### 3.4 Budget normalization guard rail (P2, cheap win)

```diff
 CAMPO belief_delta — extraer DE ESTE TURNO ÚNICAMENTE:
 Solo lo que el usuario dijo en el mensaje actual. Si no lo mencionó, null.
 Valores canónicos: operation → "alquiler"|"venta"; property_type → "departamento"|"casa"|"ph"|"terreno".
+budget_max SIEMPRE en pesos completos: "300 mil"/"300 lucas" → 300000; "1.5 palos" → 1500000.
+Si el número es ambiguo (ej: "hasta 300"), interpretá miles para alquiler (300000) y aclaralo
+en la respuesta.
```

### 3.5 Photos-without-selection guard rail (supports #2/#3)

```diff
 4. Referencias por posición ("la primera", "la segunda", "el 3") o descripción: tomá el id del
    campo ultima_busqueda del estado, poné selected_property_id y ejecutá get_property_details
    o get_property_images de una.
+4b. Si piden fotos/detalles y NO hay propiedad seleccionada NI ultima_busqueda en el estado,
+    NO llames la herramienta con un id inventado: action:clarify y preguntá cuál propiedad
+    (u ofrecé buscar primero).
```

### 3.6 Mid-booking interruption few-shot (supports #10/#13)

```diff
+Interrupción durante el agendado (responder y retomar):
+estado: {propiedad_seleccionada:7, esperando:scheduling_time, visita_dia:"jueves"}
+usuario: "¿aceptan mascotas?"
+BUENO → intent:knowledge, action:answer_knowledge, tool_calls:[{name:get_faq_answer,
+arguments:{"pregunta":"mascotas"}}], missing_slot:"scheduling_time" (se conserva el agendado;
+el sistema responde la FAQ y vos retomás el horario en el próximo turno).
```

---

## 4. Belief state improvements

### 4.1 Reset-on-new-search (fixes #3, the highest-impact conversation bug)

Engine step 6/7, when `"search_properties" ∈ requested` and the criteria changed:

```python
if "search_properties" in requested:
    belief.selected_property_id = turn.selected_property_id  # usually None → cleared
    if belief.awaiting in ("scheduling_day", "scheduling_time", "scheduling_confirm"):
        belief.awaiting = None
        belief.pending_scheduling = False
        belief.scheduling_day = belief.scheduling_time = ""   # keep scheduling_name
```

Written by: engine step 6. Read by: `_PROPERTY_ID_TOOLS` backfill (step 7), `_build_photo_plan` (Path 0b-photos), FSM `_derive_state`.

### 4.2 Persist scheduling slots on the engine path (fixes #10, revives FSM T-7)

The engine currently writes `awaiting` from `missing_slot` but never the slot **values**. Two writes needed:

- After step 5: if `turn.intent == "scheduling"`, run the existing `extract_scheduling_day/time` regexes (already imported for the hybrid fallback) on the user message and store into `belief.scheduling_day/time` when the matching slot was `awaiting`.
- In `_execute_tools`: when dispatching `schedule_visit`, copy `args["dia"]/args["horario"]/args["nombre"]` into `belief.scheduling_*` before execution (the LLM's reconstruction from history is the best available value; persisting it makes the next turn independent of the history window).

Read by: `_compact_state` (`visita_dia/hora/nombre` finally non-empty → the LLM stops re-asking), FSM `_derive_state` / T-7 pre-check (currently dead), loop detection.

### 4.3 Clear stale `awaiting` on topic change (fixes #13)

`awaiting` has no TTL and no non-scheduling reset. Add to engine step 6: if `turn.intent not in ("scheduling",)` and `belief.awaiting` startswith `scheduling_` and `belief.last_intent` was also non-scheduling (two consecutive off-topic turns) → `belief.awaiting = None; belief.pending_scheduling = False`.

### 4.4 Structured `last_search` instead of a 1200-char blob (fixes #21)

Replace `last_search_context = res[:1200]` with a compact list built at persist time: `[{"id":12,"tipo":"departamento","zona":"Centro","precio":250000,"dorm":2}, …]`, serialized into `[ESTADO].ultima_busqueda`. Cheaper in tokens, never truncates an entry, and gives the model clean material for comparative answers (#8) and descriptive selection.

### 4.5 Belief delta extensions (P2)

Add `bedrooms_match`, `bedrooms_max` to `BeliefDelta` + `apply_belief_delta` + `criterios` so refinement searches preserve the match mode (#25). Also consider an explicit `clear_criteria: bool` field so "sin límite de presupuesto" / "en cualquier zona" can actually remove a stored criterion — today null never clears, so a criterion can only be overwritten, never dropped.

---

## 5. Tool selection improvements (engine.py condition sketches)

### 5.1 Scope the book_step guard to schedule_visit (fixes #1)

```python
requested = {tc.name for tc in (turn.tool_calls or [])}
# Path 0b:
if action == "book_step" and "schedule_visit" in requested and not booking_succeeded:
    ...existing guard...
elif action == "book_step" and not requested and not booking_succeeded:
    ...existing "estoy recopilando" fallback...   # model said book_step but called nothing
# book_step + cancel/reschedule/get_my_appointments → fall through to must_surface (0c)
```

### 5.2 Detect requested-but-none-ran (fixes #2)

```python
# after _execute_tools:
if turn.tool_calls and not any_ran:
    skipped = [tc.name for tc in turn.tool_calls]
    # property-scoped tool without id and no selection → targeted clarify
    if set(skipped) & _PROPERTY_ID_TOOLS and not belief.selected_property_id:
        return _contract("¿De cuál propiedad querés que te muestre eso? Decime el ID o la posición en la lista.", ...)
    # otherwise replace the engine placeholder with _SAFE_CLARIFY_ES, never "Un momento..."
```

### 5.3 Gate the RAG safety-net (fixes #8)

```python
if turn.action == "answer_knowledge" and not any_ran:
    if turn.intent == "search" and belief.last_search_context:
        pass  # question is about shown results — let the plan/state answer, no RAG injection
    else:
        ...existing safety-net...
```

### 5.4 Ground synthesis in the question (fixes #7)

```python
# _synthesize_from_results(belief, tool_results, user_message, history_tail)
{"role": "user", "content":
    f"Pregunta del usuario:\n{user_message}\n\n"
    f"Resultados de herramientas:\n{tool_context}\n\n"
    "Respondé la pregunta del usuario basándote SOLO en estos resultados."}
```

### 5.5 Concatenate multi-tool results (fixes #9)

```python
# Path 0b2: collect ALL verbatim hits in tool order instead of returning the first
verbatim_parts = [r for n, r in zip(tools_used, tool_results)
                  if n in _VERBATIM_TOOLS and r and not r.startswith("Error:")]
other_results  = [r for n, r in zip(tools_used, tool_results)
                  if n not in _VERBATIM_TOOLS and n in _DATA_TOOLS and not r.startswith("Error:")]
if verbatim_parts:
    tail = await _synthesize_from_results(belief, other_results, user_message) if other_results else ""
    return "\n\n".join([*verbatim_parts, tail]).strip(), rich
```

### 5.6 All-errors path (supports #2/#17)

If every entry in `tool_results` starts with `"Error:"` → return an honest retry message naming the action ("No pude consultar las propiedades recién, ¿probamos de nuevo en un momento?") instead of falling to `_SAFE_CLARIFY_ES` (which reads as a non-sequitur) or synthesizing from error strings.

### 5.7 Verbatim-aware guard (fixes #14)

`_assemble_response` returns a third value `source: str` ("verbatim"|"synthesis"|"plan"|"fsm"); `run_guard` skips regeneration (judge may still score) when `source == "verbatim"`.

### 5.8 Stage-aware LLM-failure fallback (P1, conversation)

`_apply_fallback`'s whole-call-failure turn always says "¿qué tipo de propiedad estás buscando?" — mid-booking this is jarring context loss. Pick the clarify text from `belief.awaiting`:

```python
_AWAITING_CLARIFY = {
    "scheduling_day":  "Perdón, ¿qué día te quedaba bien para la visita?",
    "scheduling_time": "Perdón, ¿a qué hora te quedaba bien la visita?",
    "scheduling_name": "Perdón, ¿me repetís tu nombre para la visita?",
}
content = _AWAITING_CLARIFY.get(belief.awaiting, _SAFE_CLARIFY_ES)
```

---

## 6. Test recommendations (eval JSONL additions)

Regression cases for the top P0/P1 findings — each entry: conversation turns + expected action/tools + response assertions.

1. **Cancel ≠ book guard (#1):** seed an appointment → "cancelá mi visita del jueves" → expect `tools: [cancel_appointment]`, response contains cancellation confirmation, response NOT containing "recopilando los detalles".
2. **Reschedule (#1):** "cambiá mi visita a las 16" → `reschedule_appointment` surfaced verbatim-ish.
3. **Stale selection (#3):** search → "la primera" → details → new search "ahora casas en venta" → "mostrame fotos" → expect NO photos of the old ID; expect clarify or new-list property.
4. **Skipped-tool dead end (#2):** fresh session → "mostrame los detalles" → expect a clarifying question; assert response ≠ "Un momento, reviso eso.".
5. **Answer-from-results (#8):** search returning 3 results → "¿cuál es la más barata?" → expect `tools: []` (no get_faq_answer, no knowledge_retrieval), answer cites an `ID:N` from the list.
6. **Multi-intent (#9):** "busco depto en alquiler en el centro y qué requisitos piden?" → expect both `search_properties` and `get_faq_answer`; response contains the list AND requisitos.
7. **Offer acceptance (#12):** search a zone with no stock → bot offers other zones → "sí, dale" → expect `search_properties` re-run without zona; assert no smalltalk-only reply.
8. **Slot retention across interruption (#10):** select property → "el jueves" → "¿aceptan mascotas?" → FAQ answered → "a las 15, soy Ana López" → expect `schedule_visit` with `dia=jueves` (not re-asked).
9. **Gracias mid-flow (#11):** at NEED_NAME → "sí, gracias, soy Juan Pérez" → expect booking proceeds with nombre=Juan Pérez; scheduling state not cleared.
10. **Topic-change awaiting reset (#13):** start booking → "mejor mostrame casas en venta" ×2 turns → assert `[ESTADO]` no longer contains `esperando: scheduling_*` (belief snapshot assertion).
11. **Format invariants (#19, run on every eval turn):** any `$` amount matches `\$\d{1,3}(\.\d{3})*` ; `/mes` only when operation=alquiler; property references match `ID:\d+` (never `[N]`); ≤1 `?` per message; no "usted"/"puedes"/"quieres" voseo violations.
12. **Out-of-hours regression (Path D):** "el domingo a las 10" → informed rejection with the tenant's hours; follow-up "el lunes a las 10" → proceeds.
13. **Booking fallback marker (#5)** (unit, not eval): mock `create_appointment` returning `{"success": True}` without appointment → user receives a confirmation, `booking_succeeded` True.
14. **Concurrency (#4)** (integration): two messages 1.2 s apart → both `user:` entries present in history afterward.

---

## Appendix — sub-agent findings incorporated

- **Silent-failure audit** (22 findings): C-1 availability fail-open → backlog #16; C-2/C-3 raw-exception leak → #17; H-4 fallback-confirmation marker → #5; H-5/H-7 silent belief/history loss → #15; H-1/H-2 tool DB-error → generic clarify → #2/§5.6; M-3/M-6/M-8 logging promotions → #15.
- **FastAPI review**: missing `get_user_lock` on the V3 webhook path → #4; Redis `aclose()` leak → #18; webhook signature bypass → #6; rate-limiter-is-not-a-mutex and double/triple save amplification → #4.
