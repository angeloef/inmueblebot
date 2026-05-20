# Plan: InmuebleBot MCMC Mass Test v3 — Conversational AI Testing

**Date:** 2026-05-20
**Based on:** graphify graph (commit cad9f7ab) + git log (9 new commits since) + full codebase analysis
**Target:** `POST /admin/simulate` against Render production

---

## 🎯 Objectives

| Goal | Why |
|------|-----|
| Cover 8 untested tools | refine_search, recommend_properties, save_lead_info, request_human_assistance, update_user_preferences, get_user_preferences, reschedule_appointment, cancel_appointment |
| Add 3 missing Markov states | lead_capture, preferences, handoff (matching the bot's real ConversationStateEnum) |
| Add ~10 new edges | close gaps in coverage_tracker.py |
| Add 4 new profiles | profile types the current 8 don't cover |
| Add 4 new validation rules | catch leaks and hallucinations the v2 rules miss |
| Test the 9 new commits | sequential requests, pending scheduling persistence, SCHEDULING GUARD, currency default, etc. |
| Keep ~60 total sessions | ~15 min wall time at 3s/session delay |

---

## 📊 Current vs Target State

### Tools coverage

| Tool | v2 status | v3 target |
|------|-----------|-----------|
| search_properties | ✅ | ✅ keep |
| get_property_details | ✅ | ✅ keep |
| schedule_visit | ✅ | ✅ keep |
| get_property_images | ✅ | ✅ keep |
| get_faq_answer | ✅ | ✅ keep |
| get_my_appointments | ✅ | ✅ keep |
| compare_properties | ✅ | ✅ keep |
| save_lead_info | ❌ | ✅ NEW |
| request_human_assistance | ❌ | ✅ NEW |
| recommend_properties | ❌ | ✅ NEW |
| update_user_preferences | ❌ | ✅ NEW |
| get_user_preferences | ❌ | ✅ NEW |
| refine_search | ❌ | ✅ NEW |
| reschedule_appointment | ❌ | ✅ NEW |
| cancel_appointment | ❌ | ✅ NEW |

### Markov states (coverage_tracker.py currently has 9, adding 3)

| State | v2 | v3 | Bot's internal enum |
|-------|----|----|-------------------|
| idle | ✅ | ✅ | IDLE |
| qualifying | ✅ | ✅ | QUALIFYING |
| searching | ✅ | ✅ | SEARCHING |
| viewing_property | ✅ | ✅ | VIEWING_PROPERTY |
| scheduling | ✅ | ✅ | BOOKING |
| faq | ✅ | ✅ | (inferred) |
| appointments | ✅ | ✅ | (inferred) |
| cancelling | ✅ | ✅ | (inferred) |
| exit | ✅ | ✅ | COMPLETED |
| lead_capture | ❌ | ✅ | (save_lead_info tool) |
| preferences | ❌ | ✅ | (update_user_preferences tool) |
| handoff | ❌ | ✅ | HANDOFF / HUMAN_ASSISTANCE |

### New edges to add (~10)

```
viewing_property → lead_capture    (bot asks for contact info)
viewing_property → handoff          (user requests human)
scheduling → completed              (booking succeeded → exit)
searching → preferences             (user wants to save criteria)
preferences → searching             (saved prefs → new search with them)
viewing_property → exit             (details → user leaves)
Any → handoff                       (user interrupts to ask for human)
lead_capture → scheduling           (gave contact → schedule visit)
lead_capture → exit                 (gave contact → user leaves)
appointments → searching            (existing user checks appts → new search)
```

---

## 🧩 New Profiles (4 new, plus v2 updates)

### Profile 9: "Guarda lead + agenda" (save_lead_info)
```
idle → qualifying → searching → viewing_property → lead_capture → scheduling → exit
```
- User starts vague, bot qualifies
- Bot asks for contact info → save_lead_info called
- Then schedules visit
- Erratic: 20% changes phone/name mid-conversation

### Profile 10: "Pide agente humano" (handoff)
```
idle → searching → viewing_property → handoff → exit
```
- User searches, sees details, then asks to speak to a human
- request_human_assistance called
- Erratic: 15% changes mind after requesting handoff

### Profile 11: "Preferencias guardadas + recarga" (preferences)
```
idle → searching → preferences → searching → exit
```
- User searches, saves preferences
- Calls update_user_preferences and get_user_preferences
- Then searches again with saved prefs
- Erratic: 20% asks to modify saved prefs

### Profile 12: "Reprograma/cancela cita existente" (reschedule + cancel)
```
idle → appointments → rescheduling → exit
idle → appointments → cancelling → exit
```
- User checks existing appointments
- Reschedules or cancels
- Tests the hidden UUID <!--ID:N:uuid--> pattern and timezone conversion
- Erratic: 25% gives wrong UUID first

### v2 Profile updates needed

- **P1 (Alquiler errático):** Add refine_search path (user refines after first search)
- **P6 (Cliente existente):** Split into reschedule vs cancel branches; test UUID pattern
- **P8 (Compara):** Add recommend_properties path (bot recommends based on comparison)

---

## 🧪 New Validation Rules

### Rule 11: TOOL-EXISTS — recommend_properties
Phrases: `"recomiendo"`, `"te recomiendo"`, `"mejores opciones"`, `"propiedades similares"`

### Rule 12: TOOL-EXISTS — save_lead_info
Phrases: `"guardé tus datos"`, `"te registré"`, `"datos guardados"`, `"quedaste registrado"`

### Rule 13: TOOL-EXISTS — request_human_assistance
Phrases: `"paso con un asesor"`, `"te conecto con"`, `"derivar a un agente"`, `"hablar con un humano"`

### Rule 14: TOOL-EXISTS — refine_search
Phrases: `"refiné"`, `"ajusté la búsqueda"`, `"resultados más precisos"`

### Rule 15: LANGUAGE — verify AI response is in Spanish
Check that response text doesn't start with English messages like "Hello!" or "I found"
(common when the LLM config drifts or falls back to a non-Spanish prompt)

### Rule 16: NOT-STALE-CONTEXT — verify context carries across turns
If the user references a previous criteria or property, the bot shouldn't ask
"what operation?" again (detecting prompt regression)

---

## 🧬 Erratic Behavior Density (v3 upgrade)

| Behavior | v2 probability | v3 probability | Notes |
|----------|---------------|---------------|-------|
| Confused response | 20% | 20% | Same |
| Wrong/hallucinated ID | 25% | 30% | Bump — tests guard + tool error handling more |
| Intent change | 15% | 20% | Bump — tests state machine robustness |
| Typo/misspelling | 15% | 25% | Bump — tests accent-stripping & location normalization |
| Contradict preferences | — | 15% | NEW — user says "quiero casa" then "no, departamento" |
| Change mind about handoff | — | 15% | NEW — "no, dejá, seguimos" after requesting human |

---

## 🗺️ Full Edge Matrix (v3 — 29 known edges)

```
idle → qualifying
idle → searching
idle → faq
idle → appointments
qualifying → searching
searching → viewing_property
searching → idle
searching → searching              (refine_search)
searching → preferences            (NEW)
viewing_property → scheduling
viewing_property → searching
viewing_property → lead_capture    (NEW)
viewing_property → handoff         (NEW)
viewing_property → idle
scheduling → idle
scheduling → scheduling
scheduling → completed             (NEW)
faq → searching
faq → idle
appointments → scheduling          (reschedule)
appointments → cancelling
appointments → idle
appointments → searching           (NEW)
cancelling → idle
lead_capture → scheduling          (NEW)
lead_capture → idle                (NEW)
handoff → exit                     (NEW)
preferences → searching            (NEW)
Any → exit
```

---

## 📋 Session Allocation Plan

| Profile | Sessions | Expected Tools | Edge Coverage |
|---------|----------|---------------|---------------|
| 1. Alquiler errático | 5 | search, details, schedule, refine | qualifying→searching, searching→searching |
| 2. Busca compra | 4 | search, details, schedule | idle→searching, viewing→scheduling |
| 3. Vaga + intent change | 4 | search, details, FAQ, schedule | qualifying→searching, faq→searching |
| 4. FAQ → fotos → agenda | 4 | FAQ, search, details, images, schedule | idle→faq, faq→searching, viewing→lead_capture |
| 5. No encuentra | 3 | search, details | searching→idle (no results) |
| 6. Cliente existente | 5 | appointments, reschedule, cancel, search | appointments→scheduling, appointments→cancelling, appointments→searching |
| 7. Pide fotos | 4 | search, details, images, schedule | searching→viewing, viewing→scheduling |
| 8. Compara | 4 | search, compare, details, schedule, recommend | searching→viewing, viewing→scheduling, recommend path |
| 9. Guarda lead + agenda (NEW) | 4 | search, details, save_lead, schedule | viewing→lead_capture, lead_capture→scheduling |
| 10. Pide agente humano (NEW) | 3 | search, details, human_assistance | viewing→handoff, handoff→exit |
| 11. Preferencias guardadas (NEW) | 3 | search, update_prefs, get_prefs, recommend | searching→preferences, preferences→searching |
| 12. Reprograma/cancela (NEW) | 3 | appointments, reschedule, cancel | appointments→scheduling, appointments→cancelling |
| **Total** | **46** | **15 tools** | **29 edges** |

---

## 🔧 Implementation Order

1. **Update `coverage_tracker.py`** — add 3 new states, 10 new edges
2. **Update `validators.py`** — add 6 new validation rules (11-16)
3. **Add Profile 9** (lead capture) to `profiles.py`
4. **Add Profile 10** (handoff) to `profiles.py`
5. **Add Profile 11** (preferences) to `profiles.py`
6. **Add Profile 12** (reschedule/cancel) to `profiles.py`
7. **Update Profile 1** (add refine_search path)
8. **Update Profile 6** (add UUID pattern)
9. **Update Profile 8** (add recommend path)
10. **Update `orchestrator.py`** — add `completed` state mapping, bump SESSIONS_PER_PROFILE
11. **Update `run_full_test.py`** — add new stats tracking
12. Run calibration (2 sessions) → full batch (46 sessions) → report

---

## ⚠️ Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Production DB contamination (save_lead creates real leads) | Use test phone numbers (549115555xxxx) — real users won't match |
| Calendar event creation for fake appointments | schedule_visit creates real Google Calendar events — test bot must have cleanup or use test calendar |
| Human handoff notifications trigger real notifications | handoff service should be mocked or test phone suppressed |
| 46 sessions × ~4 avg turns × 25s/turn = ~77 min wall time | Reduce to 2-3 sessions per profile (30 total) if timing is tight |
| Chat history inflation in production DB | Each session's phone is unique — no cross-contamination |

---

## 📄 Deliverable

After implementation, the test suite will produce a report with:

- Total sessions / turns / wall time
- Edge coverage % (known vs visited)
- Per-profile breakdown (turns, violations)
- Per-tool coverage
- Violations by rule (top 5)
- Timing stats (avg/min/max turn time)
- Last 20 violations with context
