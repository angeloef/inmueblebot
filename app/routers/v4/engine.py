"""V4 Knowledge Agent engine — KA1: Percepción + sub-objetivos.

Single-pass schema-guided LLM call that extends V3 with:
  - sub_goals[]: ordered list of sub-objectives (multi-intent perception)
  - references{}: anaphora / selected_property_id resolution

Execution pipeline is identical to V3 (imported helpers, not duplicated).
Sub_goals are produced, persisted in BeliefStateV6.last_sub_goals, and
exposed in rich_content["sub_goals"]. KA5 will execute them in order.

LLM call budget per turn (median ≤3, same as V3):
  - Call 1 (always): V4 structured engine call
  - Call 2 (conditional): synthesis when tools ran + no response_plan
  - Call 3 (conditional, gated): quality judge + optional regen
"""

from __future__ import annotations

import json
import re
import time
from uuid import UUID

from loguru import logger

from app.routers.v4.evidence_eval import ABSTAIN_RESPONSE

# ── Safety-gate constants (verbatim from v3/engine.py) ────────────────────────

_OUT_OF_SCOPE_RESPONSE = (
    "Soy un asistente inmobiliario. "
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

_ABUSE_REDIRECT_ES = (
    "Entiendo que puedas estar molesto, pero te pido que mantengamos el respeto. "
    "Con gusto te ayudo con tu búsqueda: ¿qué tipo de propiedad estás buscando?"
)

_ABUSE_HANDOFF_ES = (
    "Para poder ayudarte mejor, voy a derivar tu consulta a uno de nuestros asesores, "
    "que se va a comunicar con vos a la brevedad. ¡Gracias por tu comprensión!"
)

_SAFE_CLARIFY_ES = (
    "Disculpá, no pude procesar tu mensaje correctamente. "
    "¿Podés contarme qué tipo de propiedad estás buscando y si querés alquilar o comprar?"
)


def _daily_cap_message(agency: str) -> str:
    de_agencia = f" de {agency}" if agency else ""
    return (
        "Por hoy alcanzaste el límite de mensajes de este asistente automático. "
        f"Un asesor{de_agencia} va a revisar tu conversación y se va a comunicar con vos "
        "a la brevedad para ayudarte personalmente. ¡Gracias por tu paciencia! 🙌"
    )


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
    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "confidence": confidence,
        "router_label": router_label,
        "latency_ms": (time.perf_counter() - start) * 1000,
    }


# ── V4 engine LLM call ────────────────────────────────────────────────────────

async def _call_engine_v4(messages: list[dict]) -> tuple:
    """Call the V4 structured engine LLM. Returns (TurnOutputV4|None, usage|None).

    Never raises — errors → (None, None). LLM Call 1.
    """
    from app.agents.cs_llm_client import get_client, get_model, max_tokens_kwarg, LLMRole
    from app.routers.v4.schema import RESPONSE_FORMAT_V4, parse_turn_output_v4

    client = get_client(LLMRole.SYNTH)
    model = get_model(LLMRole.SYNTH)

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=RESPONSE_FORMAT_V4,
            **max_tokens_kwarg(1200, LLMRole.SYNTH),  # extra headroom for sub_goals
        )
    except Exception as exc:
        logger.warning("[V4] Engine LLM call failed: {}", str(exc))
        return None, None

    usage = getattr(resp, "usage", None)
    choice = resp.choices[0] if resp.choices else None
    if not choice:
        return None, usage

    if getattr(choice.message, "refusal", None):
        logger.warning("[V4] Engine returned refusal")
        return None, usage

    content = getattr(choice.message, "content", None)
    if not content:
        return None, usage

    try:
        turn = parse_turn_output_v4(content)
        return turn, usage
    except Exception as exc:
        logger.warning("[V4] parse_turn_output_v4 failed: {}", str(exc))
        return None, usage


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_turn(
    phone: str,
    user_message: str,
    media_url: str | None = None,
    bsuid: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    """V4 Knowledge Agent engine — single-pass schema-guided LLM + sub_goals.

    Contract (matches v3 return shape):
        response_text, tools_used, rich_content, confidence, router_label, latency_ms
    Never raises.
    """
    start = time.perf_counter()

    # ── Step 0: Tenant + identity ────────────────────────────────────────────
    from app.core.tenancy import set_current_tenant
    from app.core.identity import set_current_contact

    if tenant_id is not None:
        set_current_tenant(tenant_id)
    set_current_contact(phone, bsuid)

    session_id: str = bsuid or phone

    # ── Step 1: Load belief ──────────────────────────────────────────────────
    from app.routers.v4.belief import load_belief_v6, save_belief_v6, BeliefStateV6
    from app.memory.working import clear_working_memory

    try:
        belief = await load_belief_v6(session_id)
    except Exception:
        belief = BeliefStateV6(session_id=session_id)

    # ── Step 2: Safety gates ─────────────────────────────────────────────────
    from app.core.turn_metrics import emit_turn_metrics
    from app.routers.v3.engine import _record_gate_history, _call_human_assistance

    def _emit(label: str, tools: list, conf: float) -> None:
        try:
            emit_turn_metrics(
                router="v4",
                tenant_id=str(tenant_id) if tenant_id else None,
                router_label=label,
                tools=tools,
                latency_ms=(time.perf_counter() - start) * 1000,
                confidence=conf,
            )
        except Exception:
            pass

    _empty_rich = {
        "images": [], "caption": "",
        "selected_property_id": belief.selected_property_id,
        "search_criteria": belief.search_criteria,
        "active_intents": list(belief.active_intents),
        "sub_goals": [],
    }

    # /resetmemory
    if user_message.strip().lower() == "/resetmemory":
        try:
            await clear_working_memory(session_id)
        except Exception:
            pass
        _emit("v4::reset", [], 1.0)
        return _contract(
            "✅ Memoria reiniciada. ¿En qué puedo ayudarte?",
            [], {**_empty_rich, "sub_goals": []}, 1.0, "v4::reset", start,
        )

    # Emergency
    if _is_emergency(user_message):
        logger.info("[V4] Emergency gate for {}", session_id)
        handoff_text = await _call_human_assistance("emergencia", user_message)
        _emit("v4::emergency", ["request_human_assistance"], 1.0)
        await _record_gate_history(belief, user_message, handoff_text)
        return _contract(handoff_text, ["request_human_assistance"], _empty_rich, 1.0, "v4::emergency", start)

    # Tenant profile for cap + policy
    from app.core.config import get_settings as _get_settings
    _cfg = _get_settings()
    try:
        from app.routers.v3.tenant_profile import load_tenant_profile
        _profile = await load_tenant_profile(tenant_id)
        _tz_name = getattr(_profile, "timezone", None) or "America/Argentina/Buenos_Aires"
        _agency = getattr(_profile, "agency_name", "") or ""
    except Exception:
        _tz_name = "America/Argentina/Buenos_Aires"
        _agency = ""

    # Daily cap
    _daily_cap = getattr(_cfg, "USER_DAILY_MESSAGE_CAP", 40)
    if _daily_cap and _daily_cap > 0:
        try:
            from app.core.usage_limits import incr_daily_count
            _count = await incr_daily_count(session_id, _tz_name)
        except Exception:
            _count = 0
        if _count > _daily_cap:
            _cap_msg = _daily_cap_message(_agency)
            _emit("v4::limit-daily", ["request_human_assistance"], 1.0)
            await _record_gate_history(belief, user_message, _cap_msg)
            return _contract(_cap_msg, ["request_human_assistance"], _empty_rich, 1.0, "v4::limit-daily", start)

    # Human handoff
    if _is_human_request(user_message):
        logger.info("[V4] Human handoff for {}", session_id)
        handoff_text = await _call_human_assistance("user_requested", user_message)
        _emit("v4::human-handoff", ["request_human_assistance"], 1.0)
        await _record_gate_history(belief, user_message, handoff_text)
        return _contract(handoff_text, ["request_human_assistance"], _empty_rich, 1.0, "v4::human-handoff", start)

    # Off-topic + abuse gate
    try:
        from app.routers.v3.abuse import is_abusive
        _abusive = is_abusive(user_message)
    except Exception:
        _abusive = False
    _oos = _is_out_of_scope(user_message)
    if _abusive or _oos:
        belief.offtopic_abuse_count = getattr(belief, "offtopic_abuse_count", 0) + 1
        _threshold = getattr(_cfg, "OFFTOPIC_ABUSE_HANDOFF_THRESHOLD", 5)
        if _threshold and belief.offtopic_abuse_count >= _threshold:
            _emit("v4::limit-abuse", ["request_human_assistance"], 1.0)
            await _record_gate_history(belief, user_message, _ABUSE_HANDOFF_ES)
            return _contract(_ABUSE_HANDOFF_ES, ["request_human_assistance"], _empty_rich, 1.0, "v4::limit-abuse", start)
        _redirect = _ABUSE_REDIRECT_ES if _abusive else _OUT_OF_SCOPE_RESPONSE
        _label = "v4::abuse" if _abusive else "v4::out-of-scope"
        _emit(_label, [], 1.0)
        await _record_gate_history(belief, user_message, _redirect)
        return _contract(_redirect, [], _empty_rich, 1.0, _label, start)

    # ── Step 2b: KA2 — recover memory evidence (3 levels) for this turn ───────
    # The V3 stack writes memory but never reads it back into the loop. Recover
    # episodic/persona/zone now so the LLM actually sees prior-session context.
    from app.routers.v4 import evidence as v4_evidence

    try:
        memory_items = await v4_evidence.gather_memory_evidence(phone, belief, tenant_id)
    except Exception as exc:
        # warning, not debug: a misconfigured tenant / broken Redis silently empties
        # the memory block; must be visible in prod logs without breaking the turn.
        logger.warning("[V4] gather_memory_evidence failed (non-fatal): {}", str(exc))
        memory_items = []
    memory_block = v4_evidence.render_memory_block(memory_items)

    # ── Step 3: Build messages ────────────────────────────────────────────────
    from app.routers.v4 import prompts as v4_prompts
    from app.routers.v3.engine import _compact_state, _history_messages

    state_json = json.dumps(_compact_state(belief), ensure_ascii=False)
    history = _history_messages(belief)
    tenant_policy = await v4_prompts.build_tenant_policy(tenant_id)
    messages = v4_prompts.build_messages_v4(
        v4_prompts.build_system_prompt_v4(),
        tenant_policy,
        history,
        state_json,
        user_message,
        memory_block=memory_block,
    )

    # ── Step 4: V4 engine call (LLM Call 1) ──────────────────────────────────
    turn, usage = await _call_engine_v4(messages)

    from app.routers.v3.engine import _parse_usage
    prompt_tokens, completion_tokens, cache_hit = _parse_usage(usage)

    # ── Step 5: Fallback ─────────────────────────────────────────────────────
    from app.routers.v3.engine import _apply_fallback

    tc_snapshot = belief.turn_count
    turn, extraction_source = _apply_fallback(turn, belief, user_message)
    fallback_incremented = belief.turn_count > tc_snapshot

    # ── Step 6: Apply delta + bookkeeping ────────────────────────────────────
    from app.routers.v3.belief import apply_belief_delta
    from app.core.config import get_settings

    settings = get_settings()
    belief = apply_belief_delta(belief, turn.belief_delta)

    if not fallback_incremented:
        belief.turn_count += 1

    if not fallback_incremented:
        belief.history.append(f"user: {user_message}")
    window = settings.HISTORY_WINDOW
    if len(belief.history) > window:
        belief.history = belief.history[-window:]

    prev_last_intent = getattr(belief, "last_intent", None)
    belief.last_action = turn.action
    belief.last_intent = turn.intent
    belief.action_history.append(turn.action)

    from app.routers.v3.engine import (
        _apply_new_search_reset,
        _resolve_ordinal_to_id,
        _clear_stale_scheduling_awaiting,
        _persist_scheduling_slots_from_message,
    )

    requested = {tc.name for tc in (turn.tool_calls or [])}
    if "search_properties" in requested:
        _apply_new_search_reset(belief, turn)
    elif turn.selected_property_id is not None:
        belief.selected_property_id = turn.selected_property_id
    else:
        _ord_id = _resolve_ordinal_to_id(user_message, belief.last_search_ids)
        if _ord_id is not None:
            belief.selected_property_id = _ord_id

    # Also check references.selected_property_id from V4 perception
    ref_prop_id = getattr(getattr(turn, "references", None), "selected_property_id", None)
    if ref_prop_id is not None and belief.selected_property_id is None:
        belief.selected_property_id = ref_prop_id

    if turn.missing_slot is not None:
        belief.awaiting = turn.missing_slot
    if turn.missing_slot is None and turn.action == "book_step":
        belief.awaiting = None

    _persist_scheduling_slots_from_message(belief, turn, user_message)
    _clear_stale_scheduling_awaiting(belief, turn, prev_last_intent)

    # Persist sub_goals from V4 perception
    sub_goals_raw = getattr(turn, "sub_goals", None) or []
    belief.last_sub_goals = [sg.model_dump() if hasattr(sg, "model_dump") else dict(intent=sg.intent, args_hint=sg.args_hint) for sg in sub_goals_raw]

    belief.last_updated_at = time.time()

    try:
        await save_belief_v6(belief)
    except Exception as exc:
        logger.warning("[V4] save_belief_v6 failed: {}", str(exc))

    # ── Step 7: Execute tools ────────────────────────────────────────────────
    from app.routers.v3.engine import _execute_tools, _persist_search_context

    tools_used, tool_results, any_ran, booking_succeeded = await _execute_tools(turn, belief)

    # ── Step 7b: RAG safety-net ──────────────────────────────────────────────
    from app.routers.v3.engine import _is_about_shown_results

    if turn.action == "answer_knowledge" and not any_ran and not _is_about_shown_results(turn, belief):
        try:
            from app.routers.v3.knowledge.index import search_knowledge
            _s = get_settings()
            _chunks = await search_knowledge(
                tenant_id=tenant_id,
                query=user_message,
                limit=_s.KNOWLEDGE_TOP_K,
                threshold=_s.KNOWLEDGE_SIMILARITY_THRESHOLD,
            )
            if _chunks:
                tool_results.append("\n\n".join(c["text"] for c in _chunks[:3]))
                tools_used.append("knowledge_retrieval")
                any_ran = True
        except Exception as _rag_exc:
            logger.debug("[V4] RAG safety-net failed (non-fatal): {}", str(_rag_exc))

    if "get_property_details" in tools_used or "get_property_images" in tools_used:
        belief.last_tool_called = tools_used[-1]
    if "search_properties" in tools_used:
        belief.last_tool_called = "search_properties"
        _persist_search_context(belief, tools_used, tool_results)

    # ── Step 7c: FSM post-engine guard ───────────────────────────────────────
    fsm_result = None
    try:
        from app.routers.v3.scheduling.fsm import resolve as fsm_resolve
        fsm_result = await fsm_resolve(belief, user_message, turn, booking_succeeded, tool_results, tenant_id)
        try:
            await save_belief_v6(belief)
        except Exception:
            pass
    except Exception as exc:
        logger.debug("[V4] fsm.resolve error (non-fatal): {}", str(exc))

    # ── Step 8: Assemble response ─────────────────────────────────────────────
    from app.routers.v3.engine import _assemble_response

    _fsm_booking_succeeded = fsm_result.booking_succeeded if fsm_result else booking_succeeded
    _fsm_plan = fsm_result.response_plan if (fsm_result and fsm_result.override) else None

    response_text, rich_content, response_source = await _assemble_response(
        turn, belief, tool_results, any_ran, tenant_id,
        booking_succeeded=_fsm_booking_succeeded,
        fsm_plan=_fsm_plan,
        tools_used=tools_used,
        user_message=user_message,
    )

    # Expose sub_goals in rich_content for the eval runner + KA5
    rich_content["sub_goals"] = belief.last_sub_goals
    rich_content["llm_calls"] = 1  # KA1: always 1 engine call

    # ── KA5: bounded control loop (KA2 retrieval + KA3 evaluation) ────────────
    # RAG evidence only when the turn is knowledge-flavored (avoids a redundant
    # embed on pure search/scheduling turns). On a knowledge turn that would
    # abstain, the loop widens the threshold and retries ONCE before giving up
    # (vector retrieval only — within the KA cost discipline).
    from app.routers.v4 import control as v4_control

    _s = get_settings()
    is_knowledge_turn = any(
        str(sg.get("intent", "")).lower() in {"knowledge", "answer_knowledge", "faq"}
        for sg in belief.last_sub_goals
    )
    evidence_pool, evidence_eval, retrieve_iters, _ = await v4_control.run_retrieval_loop(
        sub_goals=belief.last_sub_goals,
        memory_items=memory_items,
        action=turn.action,
        tenant_id=tenant_id,
        query=user_message,
        base_threshold=_s.KNOWLEDGE_SIMILARITY_THRESHOLD,
        rag_limit=_s.KNOWLEDGE_TOP_K,
        is_knowledge_turn=is_knowledge_turn,
    )
    rich_content["evidence_pool"] = evidence_pool
    rich_content["evidence_coverage"] = evidence_eval.to_dict()
    rich_content["retrieve_iters"] = retrieve_iters

    if evidence_eval.should_abstain:
        logger.info(
            "[V4/KA3] Abstaining on action={} reason={} confidence={:.2f}",
            turn.action, evidence_eval.abstain_reason, evidence_eval.confidence,
        )
        response_text = ABSTAIN_RESPONSE
        response_source = "abstention"

    # ── Step 8b: Quality guard ────────────────────────────────────────────────
    judge_score: float | None = None
    _booked_ok = (turn.action == "book_step" and _fsm_booking_succeeded)
    if not _booked_ok and not evidence_eval.should_abstain:
        try:
            from app.routers.v3 import guard
            guard_result = await guard.run_guard(
                action=turn.action,
                confidence=turn.confidence,
                user_message=user_message,
                response_text=response_text,
                state_json=json.dumps(_compact_state(belief), ensure_ascii=False),
                tool_results=tool_results,
                settings=settings,
                source=response_source,
            )
            from app.routers.v3.engine import _strip_markers
            response_text = _strip_markers(guard_result.response_text)
            judge_score = guard_result.judge_score
        except Exception as exc:
            logger.debug("[V4] guard.run_guard error (non-fatal): {}", str(exc))

    # ── Step 8c: Store assistant response in history ──────────────────────────
    try:
        belief.history.append(f"assistant: {response_text}")
        if len(belief.history) > window:
            belief.history = belief.history[-window:]
        await save_belief_v6(belief)
    except Exception as exc:
        logger.warning("[V4] Failed to append assistant response to history: {}", str(exc))

    # ── Step 8d: KA5 write-back — refresh episode + persona for next turn ─────
    # Closes the cross-session memory loop: KA2 reads exactly what this writes.
    # Idempotent per session, non-fatal, no LLM call.
    await v4_control.write_back(belief, phone)

    # ── Step 9: Metrics + return ─────────────────────────────────────────────
    router_label = f"v4::{turn.action}"
    try:
        from app.routers.v3.scheduling.fsm import SchedulingState as _SchedState
        if fsm_result and getattr(fsm_result, "next_state", None) == _SchedState.HANDOFF:
            router_label = "v4::human-handoff"
            if "request_human_assistance" not in tools_used:
                tools_used.append("request_human_assistance")
    except Exception:
        pass

    latency_ms = (time.perf_counter() - start) * 1000

    try:
        emit_turn_metrics(
            router="v4",
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
            judge_score=judge_score,
        )
    except Exception:
        pass

    logger.debug(
        "[V4] action={} intent={} sub_goals={} tools={} latency={:.0f}ms conf={:.2f}",
        turn.action, turn.intent, len(belief.last_sub_goals), tools_used, latency_ms, turn.confidence,
    )

    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "confidence": turn.confidence,
        "router_label": router_label,
        "latency_ms": latency_ms,
    }
