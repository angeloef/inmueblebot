# Multi-Agent Chatbot Best Practices

> Optimized for **gpt-5.4-mini** reasoning models.
> Architecture: **Orchestrator → Subagents** (single main agent dispatches specialized sub-agents for NLU tasks).
> Reference implementation: InmuebleBot (WhatsApp AI Real Estate Assistant).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Orchestrator Design](#2-orchestrator-design)
3. [Subagent Design](#3-subagent-design)
4. [Prompt Engineering for gpt-5.4-mini](#4-prompt-engineering-for-gpt-54-mini)
5. [Context & Memory Management](#5-context--memory-management)
6. [Tool Calling Architecture](#6-tool-calling-architecture)
7. [Execution Flow & Loop Control](#7-execution-flow--loop-control)
8. [Error Handling & Fallbacks](#8-error-handling--fallbacks)
9. [Performance Optimization](#9-performance-optimization)
10. [Testing & Validation](#10-testing--validation)
11. [Common Pitfalls](#11-common-pitfalls)
12. [Deployment Checklist](#12-deployment-checklist)

---

## 1. Architecture Overview

### 1.1 The Orchestrator-Subagent Pattern

```
┌─────────────────────────────────────────────────────────┐
│                   Webhook / Ingress                      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                    ORCHESTRATOR                          │
│  (RealEstateAgent / process_turn)                       │
│                                                         │
│  Responsibilities:                                      │
│  • Receive user message                                 │
│  • Load context & history                               │
│  • Build LLM prompt with tools                          │
│  • Execute tool calling loop (max N iterations)         │
│  • Handle fallbacks and error recovery                  │
│  • Fire background post-processing                      │
│  • Return structured response                           │
└──┬──────────────┬──────────────┬────────────────────────┘
   │              │              │
   ▼              ▼              ▼
┌────────┐  ┌──────────┐  ┌──────────┐
│ SUB-   │  │ SUB-     │  │ SUB-     │
│ AGENT 1│  │ AGENT 2  │  │ AGENT N  │
│ (NLU)  │  │ (Parser) │  │ (Memory) │
└────────┘  └──────────┘  └──────────┘
```

### 1.2 Three Agent Types

| Type | Example | When to Use | Model |
|------|---------|-------------|-------|
| **Main Agent** | `RealEstateAgent` | Every user message | gpt-5.4-mini (full tool set) |
| **NLU Subagents** | PreferenceExtractor, NameExtractor, DateParser | Background or inline NLU tasks | gpt-5.4-mini (temperature=0, max_tokens ≤ 200) |
| **Code-only Parsers** | regex fallbacks, location normalizer | Deterministic parsing, no LLM cost | None (sync, never raises) |

### 1.3 Key Principle: Hybrid Architecture

Every NLU component follows a hybrid pattern:

```
parse(raw_text, context)
  ├── strategy="llm"   → LLM subagent (temperature=0, fast)
  ├── strategy="code"  → Code fallback (regex, static maps, sync)
  └── strategy="hybrid"→ LLM first, code fallback on failure
```

This ensures graceful degradation — LLM handles ambiguity, code handles determinism.

---

## 2. Orchestrator Design

### 2.1 Core Loop

```
1. SAVE user message to history
2. LOAD merged context (Redis + PostgreSQL)
3. LOAD conversation history (last N messages)
4. BUILD messages array:
   a. System prompt (personality + rules + tool defs)
   b. User Context block (known preferences)
   c. Active context (selected property, pending scheduling)
   d. Last shown results (compressed: id + title)
   e. Conversation summary (RESUMEN)
   f. History (user + assistant alternating)
   g. Current user message
5. LLM CALL with tools (max MAX_TOOL_CALLS iterations)
6. FOR each tool call:
   a. Validate args (hallucination guards)
   b. Execute tool
   c. Extract rich content from result
   d. Append tool result to messages
   e. Inject Plan B guidance for next response
7. RETURN response_text + rich_content
8. FIRE background post-processing (state, preferences, tokens)
```

### 2.2 Message Array Order (Critical for Attention)

```
Position | Content                          | Why
---------|----------------------------------|-----------------------------
1        | System prompt                    | Establishes personality + rules
2        | User Context block               | Known facts about user
3        | Active property / pending info   | Task-specific context
4        | Last results (compressed)        | Reference for ID mapping
5        | RESUMEN DE CONVERSACION          | Compact state line
6        | Conversation history             | Full back-and-forth
7        | Current user message             | Fresh input
```

**gpt-5.4-mini note:** Reasoning models attend to the END of context more than the beginning. Put the current user message LAST and the most critical context (RESUMEN + User Context) RIGHT BEFORE the user message.

### 2.3 The RESUMEN Pattern

A compact state line injected as a system message right before history:

```
### RESUMEN DE CONVERSACION
Propiedad activa: [Departamento 2 ambientes] (ID=6) | Operacion: alquiler | Ubicacion: Obera
```

**Rules:**
- Inject ONLY when `len(history) >= 2` (prevents noise on first message)
- Keep it to 1 line, max 5 pipe-separated fields
- Fields: active_property, operation, location, budget, stage
- MUST be placed RIGHT before history, after all other context blocks

### 2.4 Background Post-Processing

Run AFTER returning response to user (asyncio.create_task). Never block user-perceived latency:

```python
asyncio.create_task(_background_post_processing())

async def _background_post_processing():
    # 1. Save assistant message to history
    # 2. Update state machine (allow_invalid=True)
    # 3. Update lead score
    # 4. Extract and save preferences (hybrid parser)
    # 5. Log cumulative token usage
```

**Order matters:** Save message first (user sees it), then parallel gather for state + lead + prefs.

---

## 3. Subagent Design

### 3.1 Subagent Interface

Every subagent follows the HybridParser ABC:

```python
class HybridParser(ABC):
    async def parse(self, raw: str, ctx: dict) -> ParseResult:
        """Main entry point. Routes to LLM or code based on strategy."""
        
    @abstractmethod
    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        """LLM-based extraction. temperature=0, max_tokens ≤ 200."""
        
    @abstractmethod
    def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        """Deterministic fallback. Regex/static maps. Never raises."""
```

### 3.2 ParseResult Schema

```python
@dataclass
class ParseResult:
    value: Any           # Extracted value, or None on failure
    confidence: float    # 0.0 to 1.0
    parser_used: str     # "llm", "code", or "hybrid"
    latency_ms: float    # Time in milliseconds
    llm_tokens: int      # Tokens used (0 for code-only)
    error: str | None    # Error message if failed
```

### 3.3 Subagent Prompt Constraints (CRITICAL)

Every LLM subagent call must follow these constraints:

| Parameter | Value | Why |
|-----------|-------|-----|
| `temperature` | 0 | Deterministic output. Same input = same output |
| `max_tokens` | ≤ 200 | Fast + cheap. Most extractions need 10-50 tokens |
| `response_format` | `{"type": "json_object"}` | Structured output for reliable parsing |
| Tools | None | Subagents parse text, they don't call tools |

**gpt-5.4-mini note:** When `temperature=0` with `gpt-5.x` reasoning models, the model skips the reasoning chain entirely for simple extraction tasks, making it as fast as non-reasoning models. This is a key optimization.

### 3.4 Subagent Prompt Template

```python
_SUBAGENT_SYSTEM_PROMPT = (
    "Sos un extractor especializado en [TASK] para un chatbot de bienes raices.\n"
    "Del siguiente mensaje del usuario, extrae [TARGET].\n\n"
    "Responde SOLO con JSON. Campos disponibles:\n"
    '{\n'
    '  "field1": "tipo esperado o null",\n'
    '  "field2": "tipo esperado o null"\n'
    '}\n\n'
    "Reglas:\n"
    "- Solo extrae lo que el usuario EXPRESAMENTE menciono.\n"
    "- Si no hay informacion nueva, responde con valores null.\n"
    "- Nunca inventes datos.\n"
    "- Nunca des explicaciones ni texto fuera del JSON."
)
```

**Why this works:**
- Same-language prompt matches user's language (Spanish → Spanish prompt)
- "Sos un extractor especializado en..." sets clear role
- JSON schema is explicit with examples
- "Solo extrae lo que el usuario EXPRESAMENTE menciono" prevents hallucination
- No markdown, no explanations, no extra text

### 3.5 Subagent Types in Practice

| Subagent | Strategy | Runs Inline? | Max Tokens | Output |
|----------|----------|-------------|------------|--------|
| PreferenceExtractor | hybrid | Background | 120 | `{location, operation_type, property_type, budget, bedrooms, features, qualitative}` |
| NameExtractor | hybrid | Background | 60 | `{name}` or null |
| DateParser | hybrid | Inline | 100 | `{date_str, time_str}` |
| LocationParser | hybrid | Inline | 80 | `{city}` |
| BudgetTierParser | hybrid | Inline | 80 | `{tier, min, max}` |
| PropertyReferenceResolver | hybrid | Inline | 100 | `{property_id}` |

**Inline vs Background decision matrix:**
- **Background** if the result is used on the NEXT turn (name, preferences)
- **Inline** if the result is used in the CURRENT turn (date, location, budget, reference)

---

## 4. Prompt Engineering for gpt-5.4-mini

### 4.1 Key Differences: Reasoning vs Non-Reasoning Models

| Aspect | gpt-4.x (non-reasoning) | gpt-5.x (reasoning) |
|--------|------------------------|---------------------|
| `temperature` | ✅ Sent (0.7 default) | ❌ Omitted (only default 1.0) |
| `max_tokens` | `max_tokens` param | `max_completion_tokens` param |
| `reasoning.effort` | ❌ N/A | ❌ Chat Completions doesn't support it (Responses API only) |
| Token cap | Hard limit enforced | Includes reasoning chain tokens |
| Instruction following | Line-by-line execution | Outcome-first, pattern matching |
| Negative rules | Often ignored ("don't think of a pink elephant") | Better at following "never do X" |
| System prompt position | Front-loaded | End-loaded (attends to last messages more) |

### 4.2 Router Adaptation

```python
if self._model.startswith("gpt-5."):
    kwargs["max_completion_tokens"] = max_tokens
    # DO NOT send temperature or reasoning.effort
else:
    kwargs["max_tokens"] = max_tokens
    kwargs["temperature"] = temperature
```

### 4.3 Prompt Structure (Outcome-First)

For `gpt-5.x` reasoning models, the prompt must be **outcome-first**, not rule-heavy:

```
❌ BAD (old GPT-4 style - rule-heavy):
REGLAS DE ORO:
1. NUNCA inventes IDs.
2. CRÍTICO: Siempre verifica...
3. FATAL: No hacer X...

✅ GOOD (GPT-5.5+ style - outcome-first):
# Success Criteria
The conversation is successful when:
- The user found a property matching their expressed needs
- If interested, a visit was scheduled with correct data

# Stopping Conditions
After each tool result, check:
"Can I answer the user's core request now?"

# Collaboration Style
[2-3 sentence description + GOOD/MALO example pair]
```

### 4.4 Prompt Sections (Ordered by Priority for gpt-5.x)

1. **Personality** (~5 lines) — Warm, role-specific. No NUNCA/CATALOGO/FATAL.
2. **Collaboration Style** (~8 lines) — How to guide conversation + GOOD/MALO examples
3. **Output Format** (~10 lines) — Templates for each response type
4. **Active Context** (~4 lines) — Current property, pending info
5. **Success Criteria** (~4 lines) — What "done" looks like
6. **Stopping Conditions** (~4 lines) — Decision framework
7. **Flow Rules** (~15 lines) — Step-by-step for scheduling, rescheduling
8. **Conversation Examples** (9 examples) — Few-shot behavioral patterns

**Total: ~5,000-6,000 chars** (was 14,000+ before optimization)

### 4.5 The GOOD/MALO Example Pattern

```
Ejemplo BUENO:
  Usuario: "quiero un departamento en obera"
  Vos: "Entendido, te ayudo a encontrar un departamento en Obera. ¿De cuantos dormitorios necesitas?"
Ejemplo MALO:
  Usuario: "quiero alquilar un departamento"
  Vos: "Ahi va, ya me quedo: alquiler de departamento. Dale decime ¿en que zona?"
```

**Why it works:** The LLM internalizes the pattern through contrast. Show the BAD first, then GOOD. The model imitates the GOOD pattern across all similar situations.

**Rule of thumb:** Never more GOOD/MALO pairs than there are distinct behaviors to teach. Each pair teaches ONE behavior.

### 4.6 Negative Rules: Use Sparingly

**Problem:** Too many NEGATIVE rules (`NUNCA`, `CRÍTICO`, `FATAL`) make the bot DUMBER and more TIMID.

**Rule:** Keep negative-to-positive ratio at ~1:10. Replace most negatives with positive outcomes:

```
❌ BAD: "NUNCA muestres el precio completo en la confirmación. CRÍTICO: solo el título."
✅ GOOD: "En la confirmación, mostrá solo el título de la propiedad. El usuario ya vio los detalles antes."
```

### 4.7 `### User Context` Injection

Always append known user data as the last block of the system prompt:

```python
### User Context
Nombre: Juan | Ubicacion: Obera | Operacion: alquiler | Tipo: departamento
```

**For gpt-5.x:** Add one more line telling the model to treat this as authoritative:
```
IMPORTANTE: El ### User Context contiene datos que el usuario ya proporcionó.
Tratalos como si los hubiera dicho en este mismo mensaje. Nunca preguntes por
un criterio que ya aparece aquí.
```

---

## 5. Context & Memory Management

### 5.1 Dual Store Architecture

| Store | Purpose | TTL | Fallback |
|-------|---------|-----|----------|
| Redis | Short-term context, messages, pending scheduling | 30 min | In-memory dict |
| PostgreSQL | Long-term preferences, lead score, user profile | Permanent | Silent degrade with empty defaults |

### 5.2 Redis Context Schema

```json
{
  "current_state": "searching",
  "conversation_stage": "collecting_criteria",
  "name": "Angelo",
  "location_preferences": "Obera",
  "operation_type": "alquiler",
  "property_type": "departamento",
  "budget_max": 150000,
  "bedrooms": 2,
  "selected_property_id": "18",
  "selected_property_title": "Departamento en Calle Pichulín 222",
  "last_shown_properties": [
    {"id": "18", "title": "Departamento en Calle Pichulín 222"},
    {"id": "6", "title": "Departamento 2 ambientes luminoso"}
  ],
  "pending_scheduling_info": {
    "property_id": "18",
    "date_str": "mañana",
    "time_str": "a las 10"
  },
  "updated_at": "2026-05-18T01:58:02.861Z"
}
```

### 5.3 Merged Context (Redis + PostgreSQL)

```python
async def get_merged_context(phone) -> dict:
    redis_ctx = await get_user_context(phone)
    pg_prefs = await get_user_preferences(phone)
    
    merged = {}
    for key in ["location", "operation_type", "property_type", "budget_*", "bedrooms", "name"]:
        if pg_prefs and pg_prefs.get(key):       # PostgreSQL has priority
            merged[key] = pg_prefs[key]
        elif redis_ctx.get(key):                   # Redis fallback
            merged[key] = redis_ctx[key]
    
    # State fields come only from Redis
    merged["current_state"] = redis_ctx.get("current_state", "idle")
    merged["conversation_stage"] = redis_ctx.get("conversation_stage", "new")
    
    return merged
```

**CRITICAL:** The `operation_type` field often doesn't exist in PostgreSQL's preference schema. When it's missing from PG, `pg_prefs.get("operation_type")` is None (falsy), so it correctly falls through to Redis. Verify your PG schema includes all fields your Redis context does.

### 5.4 Message History

- **Max 15 messages** (increased from 5 based on empirical testing)
- **TTL:** Same as context TTL (30 min)
- **Format:** `[{"role": "user"|"assistant", "content": "..."}, ...]`
- **Save user message BEFORE calling agent** (not after — the LLM needs it in context)
- **Save assistant message AFTER response** (in background task)

### 5.5 Context Persistence Flow

```
Turn N:
  1. save_message(phone, "user", message)     ← inline, before agent
  2. merged_context = get_merged_context(phone)
  3. history = get_recent_messages(phone)
  4. agent.process_turn(...)                    ← uses context + history
  5. return response                            ← to webhook
  6. BACKGROUND:
     a. save_message(phone, "assistant", response)
     b. extract_and_save_preferences(...)       ← updates Redis context
     c. set_state(...)                          ← updates state machine
```

---

## 6. Tool Calling Architecture

### 6.1 Tool Definition Principles

All tool descriptions must be:
1. **Outcome-first** — what happens, not how
2. **Context-aware** — when to call, when NOT to call
3. **Parameter-specific** — what each param means, with examples

```python
{
    "name": "search_properties",
    "description": "Search properties by location, budget, type, bedrooms, operation. Returns formatted list. Call when user provides 4+ criteria. This is the ONLY way to find real properties.",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City or zone (e.g. 'Posadas', 'Obera'). Known cities..."
            },
            "operation_type": {
                "type": "string",
                "enum": ["venta", "alquiler"],
                "description": "Tipo de operacion: venta o alquiler. Si el usuario no especifica, el sistema por defecto busca alquiler."
            }
        }
    }
}
```

### 6.2 Hallucination Guards

**Level 1 — Prompt:**
Include explicit instructions at the top of each tool definition about when NOT to call it.

**Level 2 — Code guard:**
Validate tool calls against the ORIGINAL user message (not the LLM's reasoning):

```python
if tool_name == "schedule_visit" and user_message:
    _sched_keywords = ["agendar", "visita", "visitar", ...]
    _user_lower = user_message.lower()
    _has_sched_intent = any(kw in _user_lower for kw in _sched_keywords)
    _is_simple_ref = any(phrase in _user_lower for phrase in ["id ", ...])
    
    if not _has_sched_intent and (_is_simple_ref or len(user_message.split()) <= 3):
        # Redirect schedule_visit → get_property_details
        tool_name = "get_property_details"
```

**Level 3 — Property ID guard:**
If the LLM hallucinates a different property_id than the one in context, force-correct:

```python
if tool_name == "schedule_visit":
    _selected = context.get("selected_property_id")
    _arg_pid = tool_args.get("property_id")
    if _selected and _arg_pid and str(_selected) != str(_arg_pid):
        tool_args["property_id"] = str(_selected)  # Force correction
```

### 6.3 Tool Loop Control

```python
MAX_TOOL_CALLS = 5

for iteration in range(MAX_TOOL_CALLS):
    # 1. Call LLM with tools
    # 2. If no tool calls: FINAL ANSWER → break
    # 3. For each tool call:
    #    a. Run hallucination guards
    #    b. Execute tool
    #    c. Extract rich content
    #    d. Append tool result to messages
    #    e. Inject Plan B guidance
    #    f. Detect consecutive same-tool loops → break
```

**Loop detection:**
```python
if len(tools_used) >= 2 and tools_used[-2] == tools_used[-1]:
    logger.warning(f"Loop detected: same tool twice: {tools_used[-1]}")
    if tool succeeded: propagate result
    else: break with fallback message
```

### 6.4 Plan B: Contextual System Messages

After EVERY tool call, inject a fresh system message guiding the NEXT response:

| After tool | Inject |
|-----------|--------|
| `search_properties` | "Terminá preguntando si quiere ver detalles de alguna" |
| `get_property_details` | "Usá los datos REALES del tool result. Preguntá si quiere agendar o ver fotos" |
| `schedule_visit` (success) | "Confirmá los detalles y preguntá si necesita algo más" |
| `get_property_images` | End the response after showing photos |

**Why Plan B works:** The injected instruction is CLOSER to the response generation point than the system prompt. The LLM processes it in context immediately, not 100+ lines away.

---

## 7. Execution Flow & Loop Control

### 7.1 Complete Turn Flow

```
WEBHOOK RECEIVE
  │
  ├── Rate limit check (per-user, 1s cooldown)
  ├── Global rate limit check (Redis sliding window, 50 RPM)
  ├── Dedup check (message_id TTL 5 min)
  │
  ├── save_message("user", message)           ← Mark A
  ├── merged_context = get_merged_context()    ← Load state + prefs
  ├── history = get_recent_messages()          ← Last N messages
  ├── Reference resolver                       ← "esa" → property ID
  │
  ├── _build_messages()                        ← Assemble prompt array
  │   ├── System prompt + User Context
  │   ├── Active property / pending info
  │   ├── Last results (compressed)
  │   ├── RESUMEN (if history >= 2)
  │   ├── History messages
  │   └── Current user message
  │
  ├── LLM CALL (with tools)                    ← Mark B (timing start)
  ├── Tool loop (max 5 iterations)
  │   ├── Validate → Execute → Extract → Plan B
  │   └── Loop detection → break
  │
  ├── response = {text, rich_content, tools}
  ├── Background task (asyncio.create_task)
  │   ├── save_message("assistant", response)
  │   ├── State machine update
  │   ├── Lead score update
  │   ├── Preference extraction
  │   └── Token logging
  │
  ├── Sanitize response (strip data URIs, paths, forbidden words)
  ├── Split at 📷 for photo flows            ← Mark C
  └── SEND to WhatsApp (text → images → follow-up)
```

### 7.2 Timing Measurements

```python
# Two key metrics:
turn_time = time.time() - start_time           # B to response ready
response_time = time.time() - start_time       # A to WhatsApp sent

logger.info(f"[Timing] phone={phone} | response_time={response_time:.2f}s | "
            f"turn={turn_time:.2f}s | tools={tools_used}")
```

**Targets:**
- `turn_time` < 3s (LLM reasoning + tool calls)
- `response_time` < 5s (including WhatsApp API latency)
- Background post-processing: 0-2s (not user-facing)

---

## 8. Error Handling & Fallbacks

### 8.1 Layered Defense

```
Layer 1: Prompt rules         (cheapest, most elegant)
Layer 2: Code guards          (reliable, catches what prompt misses)
Layer 3: Fallback responses   (degrades gracefully)
Layer 4: Dead-letter queue    (persists failed messages for retry)
```

### 8.2 Fallback Chains

```python
# 1. Main attempt
try:
    result = await agent.process_turn(...)
except Exception as e:
    # 2. Degraded fallback
    result = await _generate_response(...)
    
# 3. If even fallback fails
if not result:
    return {"response_text": DEFAULT_FALLBACK, ...}
```

### 8.3 Subagent Fallback

```python
# Hybrid strategy: LLM first, code on failure
llm_result = await parse_llm(raw, ctx)
if llm_result.value is not None:
    return llm_result
    
code_result = self.parse_code(raw, ctx)
if code_result.value is not None:
    return code_result
    
return ParseResult(None, 0.0, "hybrid", error="all strategies failed")
```

**CRITICAL:** The fallback condition must check `value is None` not `error is None`. Some LLM responses have a semantic error message (not a crash) and should still trigger the code fallback:

```python
# BEFORE (broken): only falls back on crashes/garbage
if result.value is None and result.error is None:
    code_result = self.parse_code(raw, ctx)

# AFTER (fixed): falls back on ANY failure
if result.value is None:
    code_result = self.parse_code(raw, ctx)
```

### 8.4 Anti-Hallucination Action Detection

After the LLM responds, check if it CLAIMS to have performed an action that no tool was called for:

```python
HALLUCINATION_CHECKS = [
    (["agendada", "cita agendada", ...], "schedule_visit", fallback_msg),
    (["reprogramada", "cita reprogramada", ...], "reschedule_appointment", fallback_msg),
    (["cancelada", "cita cancelada", ...], "cancel_appointment", fallback_msg),
]

for claim_phrases, required_tool, fallback in HALLUCINATION_CHECKS:
    if any(phrase in text_lower for phrase in claim_phrases):
        if required_tool not in tools_used:
            return f"{fallback}\n\n{text}"  # Prepend warning
```

### 8.5 Per-User Lock

Prevent state machine TOCTOU race from concurrent messages:

```python
async with get_user_lock(phone):
    result = await agent.process_turn(phone=phone, ...)
```

---

## 9. Performance Optimization

### 9.1 Token Budget

| Component | Target Tokens | Notes |
|-----------|---------------|-------|
| System prompt | 1,200-1,500 | Compact, outcome-first |
| User Context | 20-50 | Single line |
| Active context | 100-200 | Property + pending info |
| Last results | 200-400 | Compressed id+title |
| RESUMEN | 20-50 | Single line |
| History (15 msgs) | 1,500-3,000 | ~200 per message |
| Current message | 20-200 | User input |
| **Total prompt** | **3,000-5,000** | Keep under 5K |
| **Max completion** | **1,024** | For tool calling |
| Subagent (per call) | 50-200 | temperature=0, fast |

### 9.2 gpt-5.4-mini Specific Optimizations

| Optimization | Why | How |
|-------------|-----|-----|
| No `temperature` param | gpt-5.x reasoning models only support default 1.0 | Omit from kwargs |
| Use `max_completion_tokens` | gpt-5.x uses this instead of `max_tokens` | `if "gpt-5." in model` |
| Skip reasoning chain for simple tasks | Set temperature=0 on subagents, model skips reasoning | Only for extraction subagents |
| No `extra_body` | Chat Completions API rejects unknown params | Never send extra_body |
| End-load critical info | gpt-5.x attends more to recent messages | User Context + RESUMEN right before history |

### 9.3 Reduce Prompt Size

1. **Compress last_shown_properties** to `[{id, title}]` only — no price, no features
2. **Single-line RESUMEN** instead of verbose state dump
3. **Few-shot examples as condensed patterns** not full transcripts
4. **Tool descriptions at ~100 chars** — outcome-first, not feature-list
5. **Remove ALL .format() templates** — they cause KeyError and bloat

### 9.4 Parallel Operations

```python
# Background parallel tasks
post_tasks = [
    state_machine.set_state(phone, next_state),
    self._update_lead_score(phone, tools_used, message),
    self._extract_and_save_preferences(phone, message, prefs),
]
results = await asyncio.gather(*post_tasks, return_exceptions=True)
```

**Never block the user-facing response for background work.** Use `asyncio.create_task` and return immediately.

---

## 10. Testing & Validation

### 10.1 Test Levels

| Level | Scope | Tool | Frequency |
|-------|-------|------|-----------|
| Unit | Individual subagent | pytest | Every commit |
| Integration | Agent + tools + subagents | pytest + Docker | Every deploy |
| Monte Carlo | 30-40 multi-turn scenarios | `tests/massive_test/` | Weekly |
| Production smoke | Single turn via API | curl /admin/simulate | Every deploy |

### 10.2 Simulation Endpoint

```bash
curl -X POST \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"phone":"5491155550999","message":"Hola busco un depto","reset":true}' \
  "https://api.example.com/admin/simulate"
```

Returns `response_text + tools_used + timing` directly — no WhatsApp needed.

### 10.3 What to Test

1. **Hallucination guards** — Send "id 18", verify only `get_property_details` is called
2. **Sunday scheduling** — Verify proactive rejection before time parsing
3. **Missing criteria** — Send partial criteria, verify bot asks for what's missing
4. **Subagent fallback** — Test with and without LLM available (code-only mode)
5. **Context persistence** — Send message, wait 30s, send another, verify context loaded
6. **Concurrent messages** — Send two messages simultaneously, verify per-user lock works

---

## 11. Common Pitfalls

### 11.1 Prompt Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Too many negative rules | Bot is timid, over-explains, says "sorry" constantly | Replace NUNCA/CRÍTICO/FATAL with positive outcomes. Keep ratio < 1:10 |
| `.format()` templates | KeyError when a variable is missing | Remove all templates. Use simple string concatenation with `if` guards |
| Rules at bottom of prompt | LLM ignores them | Put critical rules near the END of system prompt (close to user message) |
| Contradictory examples | Bot alternates between behaviors | Ensure examples teach CONSISTENT patterns. Remove conflicting ones |
| Ultra-short examples | Bot doesn't generalize | Include enough detail for the pattern, but not full scripts |
| Vague tool descriptions | LLM calls wrong tool | Outcome-first: "Call when user asks X. DON'T call for Y." |

### 11.2 Architecture Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| User messages never saved | History has only assistant messages, LLM blindsided | Save user message INLINE before agent call (not in background) |
| Context not persisted | Preferences extracted but never reach Redis | Use get_user_context() + update + save_user_context(), not a non-existent method |
| PostgreSQL-Led context | PG has old/null data that overrides fresh Redis | Check `get_merged_context()` order: PG first but only if truthy. Fall through to Redis |
| RESUMEN never fires | History < 2 because user messages weren't saved | Fix user message saving. Then RESUMEN will have ≥2 messages |
| Hallucination guard only in prompt | LLM ignores rule, hallucinates anyway | Add CODE-level guard as Layer 2 for critical tool calls |
| Too many tool iterations | Token waste + latency | Set MAX_TOOL_CALLS=5 with loop detection. Break on consecutive same-tool |
| Background task save_message | Assistant message saved twice (once in task, once after) | Check all save points. Only save assistant once. |

### 11.3 gpt-5.4-mini Specific Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Sending `temperature` param | API error (gpt-5.x rejects it) | Omit `temperature` and `reasoning.effort` for gpt-5.x models |
| Using `max_tokens` instead of `max_completion_tokens` | Response truncated unexpectedly | Use `max_completion_tokens` when model name starts with "gpt-5." |
| Ultra-short completions (20 tokens) | Model barely responds, no reasoning | For gpt-5.x, set `max_completion_tokens` higher. 20 tokens is enough for "yes/no/where" but not for tool-calling responses |
| System prompt too long (>6K chars) | Model ignores bottom sections | Keep under 5,000 chars. Put critical rules at END (gpt-5.x attends to last messages) |
| Reasoning model, no visible chain | Can't debug model's thinking | Log full prompt + response. gpt-5.x doesn't expose reasoning chain in Chat Completions |
| Subagent with temperature=0 | Model refuses to extract | temperature=0 is fine for extraction. If failing, check your prompt schema matches the output format |

### 11.4 The "Double Ask" Bug (Most Common)

**Symptom:** Bot asks "¿Buscás para alquiler o compra?" even though the user already said "para alquilar" in the first message.

**Root cause chain:**
1. User message saved to history? → NO (webhook bypassed router's save_message)
2. Operation type extracted and persisted? → NO (update_context didn't exist)
3. ### User Context shows "Operacion: alquiler"? → NO (persistence failed)
4. RESUMEN shows "Operacion: alquiler"? → NO (history < 2 because user msg missing)
5. LLM sees user said "alquilar"? → NO (history only has assistant messages)

**Fix chain (in order):**
1. Save user message inline before agent call → history has user's words
2. Fix preference persistence → Redis has operation_type
3. ### User Context loads from Redis → prompt shows "Operacion: alquiler"
4. Prompt rule: "Si ### User Context dice 'Operacion: alquiler', NUNCA preguntes de nuevo"
5. RESUMEN fires (history now ≥ 2) → compact reminder

---

## 12. Deployment Checklist

### 12.1 Before Deploy

- [ ] Syntax check: `python3 -c "import py_compile; py_compile.compile('app/agents/real_estate_agent.py', doraise=True)"`
- [ ] Context persistence test: Send message → 2s wait → send another → verify preferences loaded
- [ ] Hallucination guard test: Send "id 18" → verify no schedule_visit called
- [ ] Subagent test: Set `PARSER_*=code` env vars → verify code fallback works
- [ ] Reset test phone context: `POST /admin/users/{phone}/reset`
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] If Monte Carlo: `python tests/massive_test/run_full_test.py`

### 12.2 After Deploy

- [ ] Health check: `GET /health` → 200 + "healthy"
- [ ] Smoke test: `POST /admin/simulate` with reset=true
- [ ] Logs check: No `AttributeError`, no `update_context` missing, no `CRITICAL`
- [ ] Timing check: `turn_time` < 5s for simple messages
- [ ] WhatsApp test: Send a real message to the bot number

### 12.3 Monitoring

```python
# Log these every turn:
[TIMING] phone=XXXX | response_time=1.82s | turn=1.31s | tools=[...]
[TOKENS] phone=XXXX | provider=openai | prompt=4331 | completion=33 | total=4364
[HALLUCINATION] Blocked/NONE
[SUBAGENT] PARSER_METRIC | component=PREFERENCE | strategy=hybrid | ...
```

**Alert thresholds:**
- `turn_time` > 10s → LLM hanging or tool loop
- Completion tokens = 0 → Model returned empty response
- Multiple hallucination blocks → Prompt needs strengthening
- Redis connection failures → Check REDIS_URL config

---

## Appendix: Reference Implementation

### A.1 InmuebleBot File Map

```
app/
├── agents/
│   ├── real_estate_agent.py    ← Orchestrator (process_turn, _build_messages)
│   ├── prompts.py              ← SYSTEM_PROMPT, TOOL_DEFINITIONS, get_system_prompt()
│   ├── tools.py                ← 13 tools (search, schedule, compare, etc.)
│   └── llm_router.py           ← Model-agnostic router (gpt-5.x vs gpt-4.x)
├── core/
│   ├── hybrid/                 ← Subagents (6 HybridParser implementations)
│   │   ├── base.py             ← HybridParser ABC, ParseResult
│   │   ├── preference.py       ← PreferenceExtractor
│   │   ├── name.py             ← NameExtractor
│   │   ├── location.py         ← LocationParser
│   │   ├── reference.py        ← PropertyReferenceParser
│   │   ├── budget.py           ← BudgetTierParser
│   │   └── date.py             ← DateParser
│   ├── memory.py               ← MemoryManager (Redis + PG + in-memory fallback)
│   └── state_machine.py        ← FSM (idle → searching → viewing → booking)
└── api/
    └── routes/
        └── webhook.py          ← Ingress, rate limiter, response plans
```

### A.2 Key Configuration

```yaml
# Env vars for subagent control
PARSER_NAME: "hybrid"       # code | llm | hybrid
PARSER_LOCATION: "hybrid"
PARSER_REFERENCE: "hybrid"
PARSER_BUDGET: "hybrid"
PARSER_PREFERENCE: "hybrid"
PARSER_DATE: "hybrid"

# Model
OPENAI_MODEL: "gpt-5.4-mini"
OPENAI_API_KEY: "..."

# Memory
REDIS_URL: "redis://..."
DATABASE_URL: "postgresql+asyncpg://..."
CONTEXT_TTL: 1800  # 30 minutes
```

### A.3 Key Constants

```python
MAX_TOOL_CALLS = 5
HISTORY_LIMIT = 15
MAX_PROPERTIES_SHOWN = 8
MAX_IMAGES_SEND = 4
CONTEXT_TTL = 1800  # 30 minutes
USER_RATE_LIMIT = 1.0  # seconds
GLOBAL_RATE_LIMIT = 50  # RPM
SUNDAY_WEEKDAY = 6  # datetime.weekday()
RESCHEDULE_FAILURE_LIMIT = 3
IMAGE_SEND_DELAY = 1.0  # seconds between images
PHOTO_FOLLOW_UP = "¿Tenes alguna otra consulta? O si querés podemos agendar una visita para que la veas en persona."
```

---

> **Document version:** 1.0
> **Last updated:** May 18, 2026
> **Optimized for:** gpt-5.4-mini (OpenAI Chat Completions API)
> **Reference project:** InmuebleBot — WhatsApp AI Real Estate Assistant
