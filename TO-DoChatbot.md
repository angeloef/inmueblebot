# TO-DO: InmuebleBot Chatbot v2.0

> Architecture target: state-driven, structured-output, regex-first router.
> Principle: constrain the LLM so tightly that guard code becomes unnecessary.
> Read in order. Each phase depends on the previous.

---

## Phase 1 — Foundation: State Machine + Regex Router

**Goal:** The state machine becomes the backbone. Every message flows through
deterministic state transitions before the LLM sees it. Tools are gated by state.

**Current state:** Conversation states exist (`ConversationStateEnum`) but are
used passively — the agent checks them as context flags, not as gates. The regex
router exists (`app/agents/router.py`) but its results are injected as hints,
not enforced.

### 1.1 Define the full state map

States and their legal transitions:

```
IDLE
  → QUALIFYING (greeting captured, no criteria yet)
  → SEARCHING (user gave criteria immediately)
  → FAQ (user asked about business hours/contact)
  → OUT_OF_SCOPE (regex match)
  → HUMAN_ASSISTANCE (user requested handoff)

QUALIFYING
  → SEARCHING (user provided search criteria)
  → FAQ

SEARCHING
  → VIEWING_PROPERTY (user selected a property from results)
  → SEARCHING (user asked to refine)
  → QUALIFYING (user changed their mind, wants different type)
  → SCHEDULING_ASK_DATE (user asked to visit a property)

VIEWING_PROPERTY
  → VIEWING_PROPERTY (user asked for more details/photos)
  → SCHEDULING_ASK_DATE (user asked to visit)
  → SEARCHING (user wants to see other options)

SCHEDULING_ASK_DATE
  → SCHEDULING_ASK_TIME (user gave a date)
  → VIEWING_PROPERTY (user backed out)

SCHEDULING_ASK_TIME
  → SCHEDULING_CONFIRM (user gave a time → call schedule_visit)
  → SCHEDULING_ASK_DATE (user changed the date)

SCHEDULING_CONFIRM
  → IDLE (visit confirmed)
  → SCHEDULING_ASK_DATE (visit rejected, offered alternatives)
  → SCHEDULING_ASK_NAME (tool requested name)

SCHEDULING_ASK_NAME
  → SCHEDULING_CONFIRM (name provided → retry schedule_visit)

APPOINTMENT_MANAGEMENT
  → IDLE (cancelled/rescheduled)
  → SCHEDULING_ASK_DATE (rescheduling with new date needed)

FAQ
  → IDLE (question answered)
  → QUALIFYING (user pivoted to property search)

OUT_OF_SCOPE
  → HUMAN_ASSISTANCE (auto-handoff)

HUMAN_ASSISTANCE
  → IDLE (handoff complete, agent will follow up)
```

### 1.2 Enhance the state machine

File: `app/core/state_machine.py`

- Add `get_legal_transitions(state: str) -> list[str]`
- Add `get_tools_for_state(state: str) -> list[str]` — maps each state to the
  exact subset of tools the LLM can call
- Add `transition(from_state, to_state) -> bool` — validates the transition is
  legal, logs illegal transitions as warnings

### 1.3 Make the regex router the primary dispatcher

File: `app/agents/router.py`

- `detect_stage()` already exists. It works. Keep it.
- Add `propose_transition(message, current_state, context) -> str` — given the
  current state and the message, propose the next state using regex + context
  flags (no LLM)
- Add a confidence flag to the proposal. If regex is confident (85% of cases),
  accept immediately. If ambiguous, fall through to classifier.

### 1.4 Integrate state-gated tools into the agent

File: `app/agents/real_estate_agent.py`

- Before building messages, resolve the current state
- Load only the tools allowed for that state (from `get_tools_for_state()`)
- If the LLM calls a tool not in the allowed set, log it as a critical error
  (this should never happen with structured output, but defense in depth)
- Remove: scheduling guard, property ID guard, "voy a buscar" detection
  (these become unnecessary because the LLM can't access the wrong tools and
  can't emit free text that needs regex-guarding)

### 1.5 Acceptance criteria

- [ ] Every state has `get_tools_for_state()` returning the correct tool subset
- [ ] 85%+ of messages resolve state transition via regex only
- [ ] No state-transition logic lives in the agent loop
- [ ] All existing tests pass (router, agent, classifier)
- [ ] Manual test: "hola" → QUALIFYING, "busco depto en oberá" → SEARCHING,
  "el 5" → VIEWING_PROPERTY, "agendame visita" → SCHEDULING_ASK_DATE

---

## Phase 2 — Constrain the LLM: Structured Output

**Goal:** Every LLM response is a typed JSON schema enforced at the API level.
No free text. No regex guards. No "voy a buscar" detection.

**Current state:** The LLM (`llm_router.py`) returns free text via
`LLMResponse.content`. The agent parses `tool_calls` from the API response
but the text content is unvalidated.

### 2.1 Define the response schema

File: `app/agents/schemas.py` (new)

```python
class ToolCallSchema(BaseModel):
    name: str
    arguments: dict

class AgentResponse(BaseModel):
    action: Literal["tool_call", "respond", "ask_question"]
    tool_calls: list[ToolCallSchema] = []
    response: str | None = None   # final text for the user
    question: str | None = None   # clarifying question text
    question_field: str | None = None  # "date", "time", "name", "generic"
    confidence: float = 1.0
    reasoning: str | None = None  # for debugging
```

### 2.2 Enforce at the API level

File: `app/agents/llm_router.py`

- Add `response_format` parameter to `ainvoke()`
- Use OpenAI's `response_format={"type": "json_schema", "json_schema": {...}}`
- Parse the response into `AgentResponse`, validate with Pydantic
- If validation fails, retry once with the error message injected as a system
  message
- If second attempt fails, return a safe fallback response

### 2.3 Rewrite the agent loop to consume structured output

File: `app/agents/real_estate_agent.py`

- The loop now receives `AgentResponse`, not raw `LLMResponse`
- `action="tool_call"` → execute tools, append results, continue loop
- `action="respond"` → use `response` text directly, break loop. No regex check.
- `action="ask_question"` → use `question` text, break loop
- `confidence < 0.7` → escalate (progressive escalation, Phase 7)
- Remove: `FORBIDDEN_RESPONSE_WORDS` list (not needed)
- Remove: "voy a buscar" detection (LLM can't emit ambiguous text)
- Remove: Plan B text injection (tool results are typed, Phase 3)

### 2.4 Create a system prompt factory

File: `app/agents/prompts.py`

- Replace the 544-line monolithic `SYSTEM_PROMPT` with a `get_prompt_for_state(state)`
- Each state gets a focused 15-40 line prompt
- The prompt includes the JSON schema requirement: "You MUST respond with valid
  JSON matching the schema. The 'action' field must be one of: tool_call, respond,
  ask_question."
- Keep the current prompt as `LEGACY_SYSTEM_PROMPT` for rollback

### 2.5 Acceptance criteria

- [ ] All LLM responses parse into valid `AgentResponse` schema
- [ ] Zero regex guards in the agent loop (count: 0 occurrences of FORBIDDEN_RESPONSE_WORDS checks, "voy a buscar" detection, Plan B injection)
- [ ] State-specific prompts exist for all 8+ states
- [ ] Manual test: a full conversation from greeting → search → detail → schedule
  with no guard activations
- [ ] Rollback path: LEGACY_SYSTEM_PROMPT + old loop can be re-enabled via config flag

---

## Phase 3 — Clean Data Flow: Typed Tool Results

**Goal:** Tools return typed dataclasses → serialized as structured JSON in the
LLM context. The LLM receives data, not formatted strings to parse.

**Current state:** Tools return Spanish formatted strings. The agent injects
Plan B system messages telling the LLM to use the exact text. The LLM has to
parse strings to extract data it needs for follow-up calls.

### 3.1 Define tool result types

File: `app/agents/tool_results.py` (new)

```python
@dataclass
class PropertySummary:
    id: str
    title: str
    price: int
    currency: str
    location: str
    bedrooms: int | None
    bathrooms: int | None
    area_m2: int | None
    property_type: str
    operation_type: str

@dataclass
class SearchToolResult:
    properties: list[PropertySummary]
    total_count: int
    criteria_applied: dict
    fallback_applied: bool
    user_message: str  # pre-formatted for the user

@dataclass
class DetailToolResult:
    property: PropertySummary
    description: str
    image_count: int
    user_message: str

@dataclass
class ScheduleToolResult:
    status: Literal["confirmed", "needs_date", "needs_time", "needs_name", "rejected"]
    appointment_id: str | None
    property_title: str
    date: str | None
    time: str | None
    missing_field: str | None  # "date", "time", "name"
    rejection_reason: str | None
    alternatives: list[str]  # suggested alternative dates
    user_message: str
```

### 3.2 Wrap all tool implementations

File: `app/agents/tools.py`

- Each tool function returns its typed result dataclass (not a string)
- `execute_tool()` in `tools.py` serializes the dataclass to a JSON string
  for the LLM context
- The `user_message` field is the pre-formatted Spanish text — extracted by the
  agent for the final response, not parsed by the LLM

### 3.3 Update agent loop to use typed results

File: `app/agents/real_estate_agent.py`

- Tool results are appended to messages as structured JSON: `json.dumps(asdict(result))`
- The LLM sees fields like `properties`, `criteria_applied`, `fallback_applied`
  as structured data — it can reference `result.properties[0].title` in its reasoning
- When the LLM responds with `action="respond"`, the agent extracts `user_message`
  from the last tool result (or uses the LLM's own text if it reformulates)
- Remove: Plan B injection entirely (the LLM receives typed data, not text to parse)

### 3.4 Acceptance criteria

- [ ] All 11 tools return typed dataclasses
- [ ] `execute_tool()` serializes results to JSON for the LLM context
- [ ] Zero Plan B system-message injections remain
- [ ] Manual test: search → LLM sees structured property list → responds correctly

---

## Phase 4 — Infrastructure: Async Worker Architecture

**Goal:** The webhook handler acknowledges WhatsApp in <100ms and enqueues
work. A worker pool processes agent turns asynchronously. WhatsApp's timeout
is no longer a constraint.

**Current state:** Everything runs synchronously in the webhook handler.
A slow LLM call blocks the response. WhatsApp retries if it takes >20s.

### 4.1 Choose a queue backend

Decision: Redis (already in the stack — used for conversation context).

- Use Redis Lists for the task queue: `LPUSH inmueblebot:message_queue {task}`
- Use Redis Streams if we later need consumer groups for horizontal scaling
- No new infrastructure dependency

### 4.2 Create the edge handler

File: `app/api/routes/webhook.py`

- Receive WhatsApp message → parse → validate → dedup (all current logic)
- Serialize the task: `{"phone": "...", "text": "...", "media_url": null, "timestamp": ...}`
- `LPUSH inmueblebot:message_queue {json.dumps(task)}`
- Return 200 OK immediately (no agent processing)
- Optionally: send typing indicator via WhatsApp API while message is queued

### 4.3 Create the worker

File: `app/workers/chat_worker.py` (new)

```python
async def run_worker():
    while True:
        task = await redis.blpop("inmueblebot:message_queue", timeout=5)
        if task is None:
            continue
        message = json.loads(task)
        async with per_user_lock(message["phone"]):
            result = await router.process_message(
                phone=message["phone"],
                message_text=message["text"],
                media_url=message.get("media_url")
            )
            await whatsapp_client.send_message(
                to=message["phone"],
                text=result["response_text"]
            )
```

- Run as a separate process: `python -m app.workers.chat_worker`
- Configurable number of workers via `CHAT_WORKER_COUNT` env var
- Each worker has its own Redis connection, PostgreSQL session factory, LLM client

### 4.4 Session affinity

- The `per_user_lock` in Redis (`SETNX inmueblebot:user_lock:{phone}`) ensures
  messages from the same user are processed in order
- No worker-stealing race conditions on a single user's conversation

### 4.5 Health check and graceful shutdown

- Worker heartbeat to Redis every 30s
- On SIGTERM: finish current task, then exit
- Health check endpoint: `GET /health/workers` → shows active worker count,
  queue depth, last heartbeat times

### 4.6 Docker compose

File: `docker-compose.yml`

- Add `chat_worker` service with `replicas: 2`
- Depends on Redis + PostgreSQL
- Same image as the web service, different entrypoint

### 4.7 Acceptance criteria

- [ ] Webhook handler returns 200 in <50ms (measured)
- [ ] Worker processes messages from the queue
- [ ] WhatsApp typing indicator sent before processing starts
- [ ] Two workers process different users' messages concurrently
- [ ] Same user's messages are serialized (no race conditions)
- [ ] Queue depth monitoring in place
- [ ] Graceful shutdown: current task completes before exit

---

## Phase 5 — Memory & Context: Summarization + Graph

**Goal:** Conversation memory is bounded (N recent messages + summaries of older
turns). Context is a property graph, not flat key-value fields.

**Current state:** Full message history up to 15 messages loaded every turn.
Context is flat key-value in Redis + PostgreSQL columns. No relationship data.

### 5.1 Sliding window with background summarization

File: `app/core/memory.py`

- Keep last 5 turns in full message format
- Turns 6-N: store as a compressed summary string
- After each turn, if total messages > 10, trigger background summarization

Summarizer logic:
```
Input: messages from turns 6-10
Output: "Usuario busca departamento en Oberá. Presupuesto 150-200k ARS.
         2-3 dormitorios. Vio propiedades ID:5, ID:8, ID:9. Preguntó por fotos
         de ID:5. No agendó visita aún."
```

- Use `gpt-4o-mini` for summarization (cheap, fast, <$0.001 per summary)
- Store summary in Redis: `inmueblebot:summary:{phone}`
- Agent prompt: inject "### Resumen de conversación anterior: {summary}"
  above the recent messages

### 5.2 Memory as a property graph

File: `app/core/graph_memory.py` (new)

Store relationships, not just facts:

```
User:{phone}
  preferences: {budget_max, bedrooms, operation_type, ...}
  viewed_properties: [{property_id, timestamp, duration}]
  scheduled_appointments: [{appointment_id, property_id, status, timestamp}]
  conversation_stage: current state
  last_activity: timestamp

Property:{id}
  similar_to: [property_ids]  (computed offline)
  viewed_by: [{phone, timestamp}]
  scheduled_by: [{phone, appointment_id}]
```

Storage: RedisGraph (if available) or Redis Hashes + Sets for relationships.

Query examples:
- "What properties similar to the last one the user viewed?"
  → `GRAPH.QUERY inmueblebot "MATCH (p:Property)-[:SIMILAR_TO]->(s:Property) WHERE p.id = $last_viewed RETURN s"`
- "What did this user do last time?"
  → Single graph traversal instead of 3 Redis GETs + 1 PostgreSQL query

### 5.3 Acceptance criteria

- [ ] Conversations with 20+ turns maintain stable token usage (<3K context tokens)
- [ ] Summaries capture key facts: preferences, viewed properties, pending actions
- [ ] Graph query for "similar properties to last viewed" returns correct results
- [ ] Memory fallback: if graph is unavailable, fall back to flat key-value

---

## Phase 6 — Quality & Operations: Observability

**Goal:** Every turn is a trace. Debugging is querying, not grepping.

**Current state:** `logger.info()` scattered throughout. Debugging means
grepping logs by phone number and mentally reconstructing the flow.

### 6.1 Instrument with OpenTelemetry

File: `app/core/tracing.py` (new)

Spans per turn:
```
Turn "{phone} — {message[:30]}"
├── webhook.parse (0.5ms)
├── webhook.dedup (0.05ms)
├── webhook.rate_limit (0.1ms)
├── router.state_transition (0.3ms)
│   ├── regex.match (0.1ms)
│   └── [conditional] classifier.llm_call (400ms)
├── context.assemble (15ms)
│   ├── redis.get_context (3ms)
│   ├── redis.get_summary (2ms)
│   └── postgresql.get_user (10ms)
├── agent.loop (total: 8.2s, iterations: 3)
│   ├── llm.call[1] (1.2s, 3400 tokens, model=gpt-4o-mini, state=SEARCHING)
│   │   └── response: action=tool_call, tools=[search_properties]
│   ├── tool.search_properties (120ms, 8 results)
│   ├── llm.call[2] (0.8s, 1200 tokens)
│   │   └── response: action=respond, confidence=0.94
│   └── llm.call[3] (0.6s, 800 tokens)
│       └── response: action=ask_question, field=generic
├── whatsapp.send (200ms)
└── context.save (8ms)
    ├── redis.save_context (5ms)
    └── postgresql.update_last_interaction (3ms)
```

Attributes on every span:
- `phone` (hashed)
- `state.current` and `state.transition_to`
- `agent.iteration_count`
- `agent.tools_used`
- `llm.tokens.prompt`, `llm.tokens.completion`
- `llm.model`
- `structured_output.confidence`
- `router.method` (regex | classifier)

### 6.2 Export to observability backend

- Export to Jaeger (self-hosted, free) or OTel Collector → any backend
- Add `OTEL_EXPORTER_OTLP_ENDPOINT` env var
- If not configured, tracing is no-op (zero overhead)
- Add a `/health/tracing` endpoint to verify traces are flowing

### 6.3 Key queries to enable

- "Show me all turns where confidence < 0.8" → find conversations that need review
- "Show me turns with >3 LLM iterations" → find tool loops
- "Show me all regex router transitions in the last hour" → monitor classification health
- "Show me latency p50/p95 for webhook.parse, agent.loop, whatsapp.send"

### 6.4 Structured logging migration

- Replace `logger.info(f"...")` with structured logs: `logger.info("agent_turn_complete", extra={...})`
- Every log line has `phone_hashed`, `state`, `turn_id`
- Correlate logs with traces via `trace_id`

### 6.5 Acceptance criteria

- [ ] Every turn produces a trace with 8+ spans
- [ ] Traces visible in Jaeger (or equivalent backend)
- [ ] Key queries (confidence < 0.8, >3 iterations) return results
- [ ] No performance regression: tracing adds <5ms overhead per turn
- [ ] Structured log migration complete for agent, router, tools

---

## Phase 7 — Progressive Escalation

**Goal:** The bot escalates based on confidence, not binary failure counts.
It can express uncertainty and ask for confirmation before acting.

**Current state:** 2 failures per capability → handoff. Binary. No nuance.

### 7.1 Confidence-based escalation ladder

File: `app/agents/real_estate_agent.py`

```
Confidence > 0.9 → execute autonomously
Confidence 0.7-0.9 → execute, but append "¿Entendí bien?" confirmation
Confidence 0.5-0.7 → ask clarifying question instead of acting
Confidence < 0.5 → human handoff with full context
```

The `confidence` field comes from the structured output (Phase 2). The LLM
self-reports its confidence. The orchestrator routes based on it.

### 7.2 Confirmation pattern

When `confidence 0.7-0.9` and `action="respond"`:
- Show the response to the user
- Append confirmation prompt: "¿Entendí bien tu consulta?"
- If user confirms (affirmative: "sí", "dale", "correcto"), proceed
- If user corrects, capture the correction and retry

This is not a separate LLM call — it's a post-processing step on the structured
output.

### 7.3 Clarification pattern

When `confidence 0.5-0.7` and `action="ask_question"`:
- The LLM already produced a `question` and `question_field`
- The agent sends this to the user directly
- The `question_field` hint tells the state machine which data we're collecting

### 7.4 Handoff with structured context

When `confidence < 0.5` or escalation triggers:
- `handoff_service.trigger_handoff()` receives structured context:
  ```json
  {
    "reason": "low_confidence",
    "confidence": 0.42,
    "state": "SCHEDULING_ASK_TIME",
    "last_5_messages": [...],
    "user_context": {...},
    "conversation_summary": "..."
  }
  ```
- The agent receiving the handoff has everything they need, no repetition

### 7.5 Remove binary fail counters

- Remove `FAIL_THRESHOLD`, `increment_fail_count()`, `reset_fail_count()`
  from `app/agents/router.py`
- Replace with confidence tracking: store last N confidence values, escalate
  if trend is downward over 3 turns

### 7.6 Acceptance criteria

- [ ] Confidence values present in all structured LLM responses
- [ ] "¿Entendí bien?" appended when confidence is 0.7-0.9
- [ ] Clarifying question shown when confidence is 0.5-0.7
- [ ] Handoff includes structured context (not just "user_requested")
- [ ] No binary fail counters remain in the codebase
- [ ] Manual test: ambiguous message → clarification → correct resolution

---

## Phase 8 — Optimization: Prompt Registry with A/B Testing

**Goal:** Prompts are versioned artifacts with metrics. Changes are measured,
not guessed.

**Current state:** Prompts are Python string constants in `prompts.py`.
Changing a prompt means editing, deploying, and hoping.

### 8.1 Create the prompt registry

File: `app/agents/prompt_registry.py` (new)

Prompts stored as YAML files:

```yaml
# prompts/searching_v3.yaml
name: searching_v3
state: SEARCHING
version: 3
status: active  # active | candidate | deprecated
rollout_pct: 0.90  # % of traffic that gets this version
template: |
  ... prompt text with {variables} ...
variables:
  - user_name
  - property_type
  - location
  - budget_max
metrics:
  avg_llm_iterations: 1.4
  avg_tokens_per_turn: 3200
  tool_call_accuracy: 0.97
  user_satisfaction: null  # requires user feedback collection
```

### 8.2 Traffic splitting

- On agent initialization, hash `phone + state + date` to determine prompt variant
- Candidate prompts get `rollout_pct: 0.10` (10% of users)
- Active prompts get `rollout_pct: 0.90`
- Hash is deterministic per user per day → same user gets consistent experience

### 8.3 Automatic metrics collection

Every prompt usage records:
- `prompt_name`, `prompt_version`
- `llm_iterations` (how many LLM calls in this turn)
- `tokens_used` (total for the turn)
- `tool_calls_made` (which tools, success/failure)
- `confidence` (from structured output)
- `escalation_triggered` (true/false)

Stored in PostgreSQL: `prompt_metrics` table.

### 8.4 Promotion workflow

When a candidate prompt outperforms the active one on key metrics for 7+ days:

1. Review: `SELECT avg(llm_iterations), avg(confidence) FROM prompt_metrics GROUP BY prompt_version WHERE prompt_name='searching' AND date > NOW() - INTERVAL '7 days'`
2. If candidate is better (fewer iterations, higher confidence, fewer escalations):
   - Update candidate YAML: `status: active`, `rollout_pct: 1.0`
   - Update old active: `status: deprecated`, `rollout_pct: 0.0`
3. Commit the YAML changes to git
4. No deploy needed (registry loads YAML from disk on change, or from DB)

### 8.5 Acceptance criteria

- [ ] All state prompts loaded from YAML registry, not Python constants
- [ ] Traffic splitting works: two users in same state see different prompts
- [ ] `prompt_metrics` table populated automatically
- [ ] Promotion workflow documented and tested
- [ ] Fallback: if YAML parsing fails, use embedded default prompt

---

## Phase 9 — Cleanup & Removal

**Goal:** Remove all code that became unnecessary because the architecture
eliminated its purpose.

### 9.1 Remove from `app/agents/real_estate_agent.py`

- [ ] `FORBIDDEN_RESPONSE_WORDS` list and associated check
- [ ] "voy a buscar" detection block (~50 lines)
- [ ] Plan B injection for search_properties results (~60 lines)
- [ ] Property ID guard (~15 lines)
- [ ] Scheduling guard (~30 lines)
- [ ] `_router_stage` / `_router_capability` as hints (state machine supersedes)
- [ ] `reschedule_failures` counter (confidence-based escalation replaces it)

### 9.2 Remove from `app/agents/router.py`

- [ ] `get_fail_count()`, `increment_fail_count()`, `reset_fail_count()`
- [ ] `FAIL_THRESHOLD`, `should_handoff()` (binary fail logic)

### 9.3 Remove from `app/core/router.py`

- [ ] `_generate_response()` — the agent loop handles all response generation now
- [ ] `_format_properties_text()`, `_format_search_results()` — tools handle this
- [ ] `_build_search_criteria()`, `_build_search_message()` — tools handle this
- [ ] `FAST_PATH_INTENTS` — state machine handles this

### 9.4 Measure the diff

- Target: agent loop shrinks from ~1548 lines to <500 lines
- Target: zero regex guards remaining
- Target: zero "defensive overrides" (property ID correction, scheduling suppression)

### 9.5 Acceptance criteria

- [ ] All removed code is deleted, not commented out
- [ ] Git diff shows net negative lines in agent + router
- [ ] All existing tests pass (update tests that referenced removed code)
- [ ] New tests cover the state machine + structured output flow

---

## Phase 10 — Testing & Validation

**Goal:** The new architecture has test coverage at every layer. Manual QA
validates the full flow before production rollout.

### 10.1 Unit tests

- [ ] `test_state_machine.py`: every state transition, illegal transitions rejected
- [ ] `test_structured_output.py`: valid `AgentResponse` parses correctly,
  invalid JSON returns fallback, schema violations retried
- [ ] `test_tool_results.py`: all 11 tools return typed dataclasses, JSON
  serialization round-trips correctly
- [ ] `test_prompt_registry.py`: YAML loading, traffic splitting determinism,
  fallback on corrupted YAML
- [ ] `test_graph_memory.py`: property graph queries, similarity lookups

### 10.2 Integration tests

- [ ] `test_full_flow.py`: greeting → search → detail → schedule, end-to-end
  with mocked LLM returning valid structured output
- [ ] `test_escalation.py`: low confidence → clarification → correct path;
  very low confidence → handoff with context
- [ ] `test_worker.py`: queue enqueue → worker dequeue → processing → WhatsApp send

### 10.3 Prompt evaluation suite

File: `tests/eval/conversations.json` (new)

A curated set of 50+ conversation scenarios with expected state transitions:
```json
[
  {
    "name": "basic_search_obera",
    "messages": [
      {"user": "hola", "expected_state": "QUALIFYING"},
      {"user": "busco un depto en oberá para alquilar", "expected_state": "SEARCHING"},
      {"user": "el de 2 ambientes", "expected_state": "VIEWING_PROPERTY"}
    ]
  }
]
```

Run against both current and new prompt versions. Flag regressions.

### 10.4 Manual QA checklist

- [ ] Full conversation: greeting → search → detail → photos → schedule (happy path)
- [ ] Ambiguous: "mostrame" with no property selected → clarification
- [ ] Out of scope: "cuánto vale mi casa?" → handoff
- [ ] Reschedule: "reprogramar mi cita" → list → select → reschedule
- [ ] Multi-intent: "fotos y agendame" → both actions in one turn
- [ ] Sunday scheduling: visit requested for Sunday → rejection → alternatives
- [ ] Long conversation: 20+ turns → memory summarization kicks in → context preserved
- [ ] Concurrent users: 3 users messaging simultaneously → correct per-user isolation
- [ ] Worker crash: kill a worker mid-turn → next message processed correctly
- [ ] Redis down: fallback to PostgreSQL-only context (graceful degradation)

### 10.5 Rollback plan

- [ ] Config flag: `CHATBOT_V2_ENABLED=false` uses legacy code path
- [ ] Legacy `SYSTEM_PROMPT` preserved as `LEGACY_SYSTEM_PROMPT`
- [ ] Legacy agent loop preserved as `process_turn_legacy()`
- [ ] Can roll back by setting one env var, no code deploy needed
- [ ] Test rollback: set flag to false → verify old behavior restored

---

## Implementation Order Summary

| Phase | Description | Dependencies | Estimated Impact |
|-------|-------------|-------------|------------------|
| 1     | State machine + regex router | None | Structural foundation |
| 2     | Structured output | Phase 1 (state-gated tools) | Eliminates 300+ lines of guards |
| 3     | Typed tool results | Phase 2 (LLM sees JSON) | Eliminates Plan B injection |
| 4     | Async worker | None (infra only) | WhatsApp timeout solved |
| 5     | Sliding window + graph | None (data layer) | Stable token usage |
| 6     | Observability | Phase 1 (tracing needs span boundaries) | Debuggability |
| 7     | Progressive escalation | Phase 2 (confidence field) | Better UX for ambiguity |
| 8     | Prompt registry + A/B | Phase 2 (state-specific prompts) | Measurable prompt quality |
| 9     | Cleanup | Phases 1-3 (guards become dead code) | Codebase simplicity |
| 10    | Testing | All phases | Confidence for rollout |

**Critical path:** 1 → 2 → 3 → 9 (these four phases eliminate the guard-code complexity)
**Parallelizable:** 4 and 5 can run alongside 1-3
**Safe to defer:** 6, 7, 8 (quality-of-life improvements, not structural)
