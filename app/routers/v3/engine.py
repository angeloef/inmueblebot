"""V3 Understanding Engine (Phase 3).

Single-pass schema-guided LLM architecture:
  1. Safety gates (regex, O(1)) — emergency / human-request / out-of-scope / /reset
  2. One structured OpenAI call (strict json_schema, gpt-5.4-mini via LLMRole.SYNTH)
     returning { belief_delta, intent, action, tool_calls, response_plan, confidence }
  3. Deterministic tool execution layer (tools listed in engine output, validated, run)
  4. Optional synthesis call if tools ran but engine gave no response_plan (≤3rd LLM call)

LLM call budget per turn:
  - Call 1 (always): engine structured call
  - Call 2 (conditional): response synthesis when tools ran + no response_plan
  (safety gates are pure regex — 0 LLM calls)

Cross-cutting guarantees:
  - set_current_tenant(tenant_id) BEFORE every Redis op → correct tenant_redis_key prefix
  - build_system_prompt() byte-identical → OpenAI prompt cache hits on every tenant/turn
  - ≤3 LLM calls/turn (see budget above)
  - run_turn never raises — all error paths return a valid contract dict
"""

from __future__ import annotations

import json
import re
import time
from uuid import UUID

from loguru import logger

# ── Safety-gate constants (verbatim from app/routers/router.py) ───────────────

_OUT_OF_SCOPE_RESPONSE = (
    "Soy un asistente inmobiliario especializado en propiedades en Oberá, Misiones. "
    "Puedo ayudarte a buscar casas, departamentos, terrenos o PH en alquiler o venta. "
    "¿En qué querés que te ayude?"
)

_OUT_OF_SCOPE_PATTERNS: list[str] = [
    r"\bnovia\b", r"\bnovio\b", r"\bcita\b.*\bamorosa\b", r"\bconseguir\b.*\bnovi",
    r"\breceta\b", r"\bcocina\b", r"\bchiste\b", r"\badivinanza\b",
    r"\bclima\b", r"\bpronóstico\b", r"\btiempo\b.*\bva a\b",
    r"\bfútbol\b", r"\bfutbol\b", r"\bpartido\b.*\bjugó\b",
    r"\bpelícula\b", r"\bserie\b.*\brecomend", r"\bmúsica\b.*\bescuchar\b",
    r"\btinder\b", r"\bbumble\b", r"\bhappn\b",
    r"\bsexo\b", r"\bsexual\b", r"\bporno\b",
    r"\bhackear\b", r"\bhacker\b", r"\bcontraseña\b.*\bolvid",
    r"\bganar\s+dinero\b", r"\binvertir\b.*\bcripto\b",
    r"\bcurriculum\b", r"\bcv\b", r"\btrabajo\b.*\bbusco\b",
]

_IN_SCOPE_KEYWORDS: list[str] = [
    "alquiler", "alquilar", "alquilo", "venta", "comprar", "vender",
    "casa", "departamento", "depto", "dpto", "terreno", "ph", "duplex",
    "propiedad", "propiedades", "inmueble", "inmobiliaria", "inmobiliario",
    "obera", "oberá", "misiones", "zona", "barrio", "dormitorio",
    "presupuesto", "precio", "fotos", "detalles", "visita", "visitar",
    "requisitos", "garantía", "garantia", "contrato", "mascota",
    "servicios", "luz", "agua", "gas", "cochera", "patio", "quincho",
    "monoambiente", "ambientes", "m²", "m2", "metros", "cubiertos",
    "agendar", "coordinamos", "mostrame", "busco", "buscando",
]

_EMERGENCY = re.compile(
    r"\b(luz cortada|sin luz|corte de luz|ascensor|atrapad[oa]|inundaci[oó]n|"
    r"se inund|p[ée]rdida de agua|fuga de gas|olor a gas|escape de gas|robo|"
    r"me robaron|emergencia|accidente|ayuda urgente|incendio|fuego|"
    r"se prende fuego|me electrocut)\b",
    re.IGNORECASE,
)

_HUMAN_REQUEST = re.compile(
    r"\b(hablar con (?:una |un )?(?:persona|humano|agente|asesor|operador|representante|alguien|encargad[oa]|due[ñn][oa])"
    r"|(?:una |un )?persona real|alguien real|gente real|ser humano"
    r"|atend[ae] (?:una |un )?(?:persona|humano)"
    r"|p[aá]same? con (?:una |un |algún )?(?:persona|humano|agente|asesor|operador|representante|alguien)"
    r"|comunic[aá](?:r|me|rme)? con (?:una |un |algún )?(?:persona|humano|agente|asesor|operador|representante|alguien)"
    r"|quiero (?:un |una )?(?:agente|asesor|humano|operador|representante)"
    r"|necesito (?:un |una )?(?:agente|asesor|humano|operador|representante)"
    r"|atenci[oó]n humana|asistencia humana)\b",
    re.IGNORECASE,
)

_SAFE_CLARIFY_ES = (
    "Disculpá, no pude procesar tu mensaje correctamente. "
    "¿Podés contarme qué tipo de propiedad estás buscando y si querés alquilar o comprar?"
)

# ── Gate helpers ──────────────────────────────────────────────────────────────

def _is_emergency(message: str) -> bool:
    return bool(_EMERGENCY.search(message or ""))


def _is_human_request(message: str) -> bool:
    return bool(_HUMAN_REQUEST.search(message or ""))


def _is_out_of_scope(message: str) -> bool:
    msg_lower = (message or "").lower().strip()
    if any(kw in msg_lower for kw in _IN_SCOPE_KEYWORDS):
        return False
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, msg_lower):
            return True
    return False


# ── Contract builder ──────────────────────────────────────────────────────────

def _contract(
    response_text: str,
    tools_used: list[str],
    rich_content: dict,
    confidence: float,
    router_label: str,
    start: float,
) -> dict:
    """Build the return dict matching the V2 contract shape."""
    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "confidence": confidence,
        "router_label": router_label,
        "latency_ms": (time.perf_counter() - start) * 1000,
    }


def _empty_rich(belief) -> dict:
    """Minimal rich_content with all V2 contract sub-keys."""
    return {
        "images": [],
        "caption": "",
        "selected_property_id": getattr(belief, "selected_property_id", None),
        "search_criteria": getattr(belief, "search_criteria", {}),
        "active_intents": list(getattr(belief, "active_intents", set())),
    }


# ── State serialisation for context injection ─────────────────────────────────

def _compact_state(belief) -> dict:
    """Extract only derived facts needed for the engine context.

    No history duplication — history is already in the message list.
    """
    state: dict = {}
    if belief.search_criteria:
        state["criterios"] = belief.search_criteria
    if belief.selected_property_id is not None:
        state["propiedad_seleccionada"] = belief.selected_property_id
    if belief.last_search_context:
        state["ultima_busqueda"] = belief.last_search_context
    if getattr(belief, "awaiting", None):
        state["esperando"] = belief.awaiting
    if getattr(belief, "last_action", None):
        state["ultima_accion"] = belief.last_action
    if getattr(belief, "last_intent", None):
        state["ultimo_intent"] = belief.last_intent
    if belief.scheduling_day:
        state["visita_dia"] = belief.scheduling_day
    if belief.scheduling_time:
        state["visita_hora"] = belief.scheduling_time
    if belief.scheduling_name:
        state["visita_nombre"] = belief.scheduling_name
    if belief.active_intents:
        state["intents_activos"] = sorted(belief.active_intents)
    state["turno"] = belief.turn_count
    return state


def _history_messages(belief) -> list[str]:
    """Return the history list (without the current message)."""
    return list(belief.history or [])


# ── Engine LLM call ───────────────────────────────────────────────────────────

async def _call_engine(messages: list[dict]) -> tuple:
    """Call the structured engine LLM and return (TurnOutput|None, usage|None).

    Never raises — errors → (None, None).
    LLM call budget: this is Call 1.
    """
    from app.agents.cs_llm_client import get_client, get_model, max_tokens_kwarg, LLMRole
    from app.routers.v3 import schema

    client = get_client(LLMRole.SYNTH)
    model = get_model(LLMRole.SYNTH)

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=schema.RESPONSE_FORMAT,
            **max_tokens_kwarg(1024, LLMRole.SYNTH),
        )
    except Exception as exc:
        logger.warning("[V3] Engine LLM call failed: {}", str(exc))
        return None, None

    usage = getattr(resp, "usage", None)

    # Check for refusal
    choice = resp.choices[0] if resp.choices else None
    if not choice:
        return None, usage

    if getattr(choice.message, "refusal", None):
        logger.warning("[V3] Engine returned refusal")
        return None, usage

    content = getattr(choice.message, "content", None)
    if not content:
        return None, usage

    try:
        turn = schema.parse_turn_output(content)
        return turn, usage
    except Exception as exc:
        logger.warning("[V3] parse_turn_output failed: {}", str(exc))
        return None, usage


# ── Fallback ──────────────────────────────────────────────────────────────────

def _apply_fallback(turn, belief, message: str):
    """Apply regex fallback when engine output is absent or incomplete.

    Returns (turn, extraction_source).
    Updates belief in-place via update_belief (which also increments turn_count
    and appends to history — see NOTE in run_turn about double-counting guard).
    """
    from app.routers.v3.schema import TurnOutput, BeliefDelta, ToolCallSpec, ResponsePlanItem

    if turn is None:
        # Whole-call failure — use regex extractor
        try:
            from app.core.state_transitioner import update_belief
            # update_belief increments turn_count and appends to history.
            # The engine's bookkeeping step will guard against double-counting
            # by checking the snapshot taken before this call.
            update_belief(belief, message)
        except Exception:
            pass

        fallback_turn = TurnOutput(
            belief_delta=BeliefDelta(
                operation=belief.operation,
                property_type=belief.property_type,
                zone=belief.zone,
                budget_max=belief.budget_max,
                bedrooms_min=belief.bedrooms_min,
            ),
            intent="search",
            action="clarify",
            tool_calls=[],
            selected_property_id=None,
            missing_slot=None,
            response_plan=[ResponsePlanItem(type="text", content=_SAFE_CLARIFY_ES)],
            confidence=0.0,
        )
        return fallback_turn, "regex_fallback"

    # Partial: check if belief_delta is all-null while message likely has criteria
    delta = turn.belief_delta
    all_null = all(
        getattr(delta, f) is None
        for f in ("operation", "property_type", "zone", "budget_max", "bedrooms_min")
    )
    if all_null:
        # Try to fill from regex extractors without mutating turn_count/history
        try:
            from app.core.state_transitioner import (
                extract_scheduling_day,
                extract_scheduling_time,
                OPERATION_PATTERNS,
                TYPE_PATTERNS,
                ZONE_PATTERNS,
            )
            msg_lower = message.lower()
            if delta.operation is None:
                for pat, val in OPERATION_PATTERNS:
                    if re.search(pat, msg_lower):
                        delta.operation = val
                        break
            if delta.property_type is None:
                for pat, val in TYPE_PATTERNS:
                    if re.search(pat, msg_lower):
                        delta.property_type = val
                        break
            if delta.zone is None:
                for pat, val in ZONE_PATTERNS:
                    if re.search(pat, msg_lower):
                        delta.zone = val
                        break
        except Exception:
            pass
        return turn, "hybrid"

    return turn, "engine"


# ── Tool execution ────────────────────────────────────────────────────────────

async def _execute_tools(turn) -> tuple[list[str], list[str], bool]:
    """Execute tool_calls from engine output deterministically.

    Returns (tools_used, tool_results, any_ran).
    Each tool is validated before execution. Unknown/invalid tools are skipped.
    execute_tool never raises (returns error string).
    Tenant scope is already set via ContextVar from step 0.
    """
    from app.tools.v2.registry import execute_tool, validate_tool_args
    from app.agents.schemas import CSStructuredToolCall

    tools_used: list[str] = []
    tool_results: list[str] = []
    any_ran = False

    for i, tc in enumerate(turn.tool_calls or []):
        args = tc.parsed_args()
        ok, err = validate_tool_args(tc.name, args)
        if not ok:
            logger.debug("[V3] Skipping tool {}: {}", tc.name, err)
            continue
        try:
            call = CSStructuredToolCall(id=f"call_{i}", name=tc.name, arguments=args)
            result = await execute_tool(call)
            tools_used.append(tc.name)
            tool_results.append(str(result))
            any_ran = True
        except Exception as exc:
            logger.warning("[V3] Tool {} error: {}", tc.name, str(exc))
            tool_results.append(f"Error: {exc}")
            tools_used.append(tc.name)

    return tools_used, tool_results, any_ran


# ── Response assembly ─────────────────────────────────────────────────────────

async def _assemble_response(
    turn,
    belief,
    tool_results: list[str],
    any_ran: bool,
    tenant_id,
) -> tuple[str, dict]:
    """Build response_text and rich_content from engine output + tool results.

    Priority:
    1. Engine response_plan (non-empty) — preferred path, 0 extra LLM calls.
    2. Synthesis call (LLM Call 2) — only when tools ran but engine has no plan.
    3. Safe default — action in clarify/smalltalk/handoff with no plan.

    Returns (response_text, rich_content).
    """
    from app.agents.cs_llm_client import get_client, get_model, max_tokens_kwarg, LLMRole
    from app.core.response_parser import get_final_response_format, parse_llm_response

    rich: dict = {
        "images": [],
        "caption": "",
        "selected_property_id": belief.selected_property_id,
        "search_criteria": belief.search_criteria,
        "active_intents": list(belief.active_intents),
    }

    # ── Path 1: engine provided a response_plan ────────────────────────
    plan = turn.response_plan or []
    if plan:
        # Check if plan has image segments
        image_segs = [p for p in plan if p.type == "images"]
        text_segs = [p for p in plan if p.type == "text"]

        if image_segs and belief.selected_property_id:
            # Resolve images from tool results or DB
            images, title = await _resolve_images(belief)
            if images:
                rich["images"] = images
                rich["caption"] = f"Fotos de '{title}'" if title else ""
                segments: list[dict] = []
                for seg in plan:
                    if seg.type == "text":
                        segments.append({"type": "text", "content": seg.content})
                    elif seg.type == "images":
                        segments.append({"type": "images", "images": images[:4], "caption": seg.content})
                rich["response_plan"] = segments
                return "", rich

        # Pure text plan
        if len(text_segs) == 1 and not image_segs:
            return text_segs[0].content, rich

        # Multi-text plan — use response_plan for sequential delivery
        segments_out: list[dict] = [
            {"type": seg.type, "content": seg.content} for seg in plan
        ]
        rich["response_plan"] = segments_out
        combined = " ".join(s.content for s in text_segs if s.content)
        return combined, rich

    # ── Path 2: tools ran but no plan → synthesis call (LLM Call 2) ──
    if any_ran and tool_results:
        try:
            compact = json.dumps(_compact_state(belief), ensure_ascii=False)
            tool_context = "\n".join(
                f"[{i+1}] {r}" for i, r in enumerate(tool_results)
            )
            synth_messages = [
                {
                    "role": "system",
                    "content": (
                        "Sos ChatbotSerio, asistente inmobiliario en Oberá. "
                        "Usá los resultados de las herramientas para dar una respuesta clara y amigable al usuario. "
                        "Respondé SIEMPRE en español. Sé conciso y profesional."
                    ),
                },
                {
                    "role": "system",
                    "content": f"[ESTADO]\n{compact}",
                },
                {
                    "role": "user",
                    "content": (
                        f"Resultados de herramientas:\n{tool_context}\n\n"
                        "Respondé al usuario basándote en estos resultados."
                    ),
                },
            ]
            client = get_client(LLMRole.SYNTH)
            model = get_model(LLMRole.SYNTH)
            resp = await client.chat.completions.create(
                model=model,
                messages=synth_messages,
                response_format=get_final_response_format(),
                **max_tokens_kwarg(512, LLMRole.SYNTH),
            )
            content = resp.choices[0].message.content if resp.choices else ""
            if content:
                text, _ = parse_llm_response(content)
                if text:
                    return text, rich
        except Exception as exc:
            logger.warning("[V3] Synthesis call failed: {}", str(exc))

    # ── Path 3: safe default for clarify/smalltalk/handoff ────────────
    return _SAFE_CLARIFY_ES, rich


async def _resolve_images(belief) -> tuple[list[str], str]:
    """Fetch image URLs for the selected property from the tool."""
    prop_id = getattr(belief, "selected_property_id", None)
    if not prop_id:
        return [], ""
    try:
        from app.tools.v2.get_property_images import get_property_images
        raw = await get_property_images(property_id=prop_id)
        parsed = json.loads(raw)
        return parsed.get("images", []), parsed.get("title", "")
    except Exception:
        return [], ""


# ── Emergency tool helper ─────────────────────────────────────────────────────

async def _call_human_assistance(reason: str, message: str) -> str:
    """Call request_human_assistance tool safely. Returns the response string."""
    try:
        from app.tools.v2.request_human_assistance import request_human_assistance
        return await request_human_assistance(reason=reason, message=message)
    except Exception:
        return "Te comunico con un asesor de inmediato."


# ── Metrics helper ────────────────────────────────────────────────────────────

def _parse_usage(usage) -> tuple[int | None, int | None, bool | None]:
    """Extract (prompt_tokens, completion_tokens, cache_hit) from usage object."""
    if usage is None:
        return None, None, None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    # prompt_tokens_details.cached_tokens — guard with getattr
    ptd = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(ptd, "cached_tokens", None) if ptd else None
    cache_hit = bool(cached and cached > 0)
    return prompt_tokens, completion_tokens, cache_hit


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_turn(
    *,
    phone: str,
    user_message: str,
    media_url: str | None = None,
    bsuid: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    """V3 Understanding Engine — single-pass schema-guided LLM.

    Contract (matches v2_adapter.process_turn_v2 return shape):
        response_text:  str
        tools_used:     list[str]
        rich_content:   dict {images, caption, selected_property_id,
                              search_criteria, active_intents[, response_plan]}
        confidence:     float
        router_label:   str
        latency_ms:     float

    Never raises.
    """
    start = time.perf_counter()

    # ── Step 0: Tenant + identity ────────────────────────────────────────────
    from app.core.tenancy import set_current_tenant
    from app.core.identity import set_current_contact

    if tenant_id is not None:
        set_current_tenant(tenant_id)
    # Defensive: adapter already calls set_current_contact, but ensure it for
    # direct engine invocations too.
    set_current_contact(phone, bsuid)

    session_id: str = bsuid or phone

    # ── Step 1: Load belief ──────────────────────────────────────────────────
    from app.routers.v3.belief import load_belief_v5
    from app.memory.working import clear_working_memory

    try:
        belief = await load_belief_v5(session_id)
    except Exception:
        from app.routers.v3.belief import BeliefStateV5
        belief = BeliefStateV5(session_id=session_id)

    # ── Step 2: Safety gates ─────────────────────────────────────────────────
    from app.core.turn_metrics import emit_turn_metrics

    def _emit_gate(label: str, tools: list, conf: float) -> None:
        try:
            emit_turn_metrics(
                router="v3",
                tenant_id=str(tenant_id) if tenant_id else None,
                router_label=label,
                tools=tools,
                latency_ms=(time.perf_counter() - start) * 1000,
                confidence=conf,
            )
        except Exception:
            pass

    # /resetmemory
    if user_message.strip().lower() == "/resetmemory":
        logger.info("[V3] /resetmemory triggered for {}", session_id)
        try:
            await clear_working_memory(session_id)
        except Exception:
            pass
        _emit_gate("v3::reset", [], 1.0)
        return _contract(
            "✅ Memoria reiniciada. ¿En qué puedo ayudarte?",
            [], {"images": [], "caption": "", "selected_property_id": None,
                 "search_criteria": {}, "active_intents": []},
            1.0, "v3::reset", start,
        )

    # Emergency
    if _is_emergency(user_message):
        logger.info("[V3] Emergency handoff for {}: {}", session_id, user_message[:80])
        handoff_text = await _call_human_assistance("emergencia", user_message)
        _emit_gate("v3::emergency", ["request_human_assistance"], 1.0)
        return _contract(
            handoff_text,
            ["request_human_assistance"],
            {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
             "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
            1.0, "v3::emergency", start,
        )

    # Human handoff
    if _is_human_request(user_message):
        logger.info("[V3] Human handoff for {}: {}", session_id, user_message[:80])
        handoff_text = await _call_human_assistance("user_requested", user_message)
        _emit_gate("v3::human-handoff", ["request_human_assistance"], 1.0)
        return _contract(
            handoff_text,
            ["request_human_assistance"],
            {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
             "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
            1.0, "v3::human-handoff", start,
        )

    # Out of scope
    if _is_out_of_scope(user_message):
        logger.info("[V3] Out-of-scope blocked for {}: {}", session_id, user_message[:80])
        _emit_gate("v3::out-of-scope", [], 1.0)
        return _contract(
            _OUT_OF_SCOPE_RESPONSE,
            [],
            {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
             "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
            1.0, "v3::out-of-scope", start,
        )

    # ── Step 3: Build messages ────────────────────────────────────────────────
    from app.routers.v3 import prompts

    state_json = json.dumps(_compact_state(belief), ensure_ascii=False)
    history = _history_messages(belief)
    messages = prompts.build_messages(
        prompts.build_system_prompt(),
        prompts.build_tenant_policy(tenant_id),
        history,
        state_json,
        user_message,
    )

    # ── Step 4: Engine call (LLM Call 1) ─────────────────────────────────────
    turn, usage = await _call_engine(messages)
    prompt_tokens, completion_tokens, cache_hit = _parse_usage(usage)

    # ── Step 5: Fallback ─────────────────────────────────────────────────────
    # Snapshot turn_count BEFORE fallback (update_belief may increment it)
    tc_snapshot = belief.turn_count
    turn, extraction_source = _apply_fallback(turn, belief, user_message)
    # After fallback: if update_belief ran, turn_count was already incremented.
    # We track the snapshot and skip the explicit increment in step 6 if needed.
    fallback_incremented = belief.turn_count > tc_snapshot

    # ── Step 6: Apply delta + bookkeeping ────────────────────────────────────
    from app.routers.v3.belief import apply_belief_delta, save_belief_v5
    from app.core.config import get_settings

    settings = get_settings()
    belief = apply_belief_delta(belief, turn.belief_delta)

    # Single turn_count incrementer (guard against double-count from fallback)
    if not fallback_incremented:
        belief.turn_count += 1

    # History append (guard if fallback already appended)
    if not fallback_incremented:
        belief.history.append(user_message)
    window = settings.HISTORY_WINDOW
    if len(belief.history) > window:
        belief.history = belief.history[-window:]

    # Engine-tracking fields
    belief.last_action = turn.action
    belief.last_intent = turn.intent
    belief.action_history.append(turn.action)

    # selected_property_id
    if turn.selected_property_id is not None:
        belief.selected_property_id = turn.selected_property_id

    # missing_slot → awaiting
    if turn.missing_slot is not None:
        belief.awaiting = turn.missing_slot

    # Scheduling slots from missing_slot feedback
    if turn.missing_slot is None and turn.action == "book_step":
        # Scheduling completed or no slot missing — clear awaiting
        belief.awaiting = None

    belief.last_updated_at = time.time()

    try:
        await save_belief_v5(belief)
    except Exception as exc:
        logger.warning("[V3] save_belief_v5 failed: {}", str(exc))

    # ── Step 7: Execute tools ────────────────────────────────────────────────
    tools_used, tool_results, any_ran = await _execute_tools(turn)

    # Update belief with tool side-effects
    if "get_property_details" in tools_used or "get_property_images" in tools_used:
        # Update last_tool_called for state_label compat
        belief.last_tool_called = tools_used[-1]
    if "search_properties" in tools_used:
        belief.last_tool_called = "search_properties"

    # ── Step 8: Assemble response ─────────────────────────────────────────────
    response_text, rich_content = await _assemble_response(
        turn, belief, tool_results, any_ran, tenant_id
    )

    # ── Step 9: Metrics + return ─────────────────────────────────────────────
    router_label = f"v3::{turn.action}"
    latency_ms = (time.perf_counter() - start) * 1000

    try:
        emit_turn_metrics(
            router="v3",
            tenant_id=str(tenant_id) if tenant_id else None,
            router_label=router_label,
            action=turn.action,
            tools=tools_used,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit=cache_hit,
            confidence=turn.confidence,
            extraction_source=extraction_source,
        )
    except Exception:
        pass

    logger.debug(
        "[V3] action={} intent={} tools={} latency={:.0f}ms conf={:.2f} src={}",
        turn.action, turn.intent, tools_used, latency_ms, turn.confidence, extraction_source,
    )

    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "confidence": turn.confidence,
        "router_label": router_label,
        "latency_ms": latency_ms,
    }
