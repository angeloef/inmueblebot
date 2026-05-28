"""Dual router — S1 + Coordinator (multi-agent Phase 8)."""

import re
import time

from loguru import logger

from app.agents.schemas import CSAgentResponse as AgentResponse, ChatResponse
from app.core.belief_state import (
    ConversationBeliefState,
    get_belief,
    is_session_stale,
    SESSION_INACTIVITY_TIMEOUT,
)
from app.core.context_aggregator import build_context_prompt
from app.core.state_transitioner import update_belief
from app.memory.working import save_working_memory, load_working_memory, clear_working_memory
from app.memory.episodic import build_greeting_from_episodes
from app.memory.user_model import build_personalized_context
from app.routers.system1 import format_response, match_pattern
from app.agents.s2_agent import process_message, process_message_multistep
from app.agents.coordinator import coordinate, _build_scheduling_context
from app.agents.conversation_manager import (
    save_specialist_state,
    get_saved_state,
    clear_saved_state,
)

S1_CONFIDENCE_THRESHOLD = 0.70


def _clear_scheduling_state(belief: ConversationBeliefState) -> None:
    """Clear scheduling state after completion or escape."""
    belief.scheduling_name = ""
    belief.scheduling_phone = ""
    belief.scheduling_day = ""
    belief.scheduling_time = ""
    belief.scheduling_loop_count = 0
    belief.active_intents.discard("scheduling")


def _extract_property_data(belief, result_text: str) -> None:
    """Extract key property data lines from a get_property_details result."""
    import re
    lines = result_text.split("\n")
    key_lines = [l.strip() for l in lines if any(
        kw in l.lower() for kw in ["$", "córdoba", "san martín", "misiones", 
                                     "servicios", "electricidad", "agua", "gas", 
                                     "internet", "dormitorio", "m²"]
    )][:5]
    if key_lines:
        belief.last_property_data = " | ".join(key_lines)[:300]


async def _try_pre_llm_shortcut(
    belief: ConversationBeliefState, message: str, session_id: str, phone: str = ""
) -> tuple | None:
    """Try to handle the message deterministically without calling the LLM.
    
    Returns (ChatResponse, tools_called, confidence, router_label) or None.
    """
    import re
    from app.agents.schemas import MessageChunk
    from app.tools.v2.get_property_details import get_property_details
    from app.tools.v2.schedule_visit import schedule_visit
    
    msg_lower = message.lower().strip()
    
    # Case 1: Property resolved by description → show details immediately
    if "resolved_by_description" in (belief.active_intents or set()) and belief.selected_property_id:
        # Check if user is asking for something DIFFERENT (new criteria)
        msg_lower = message.lower().strip()
        new_search_kw = ["busca", "buscando", "estoy buscando", "tienen", "alguno", "algun", "otro", "otra", 
                         "diferente", "2 ambientes", "3 dormitorios", "habitacion",
                         "1 habitacion", "1 dormitorio", "2 dormitorios", "de 1", "de 2"]
        if any(kw in msg_lower for kw in new_search_kw):
            belief.active_intents.discard("resolved_by_description")
            belief.selected_property_id = None  # Prevent re-resolution
            belief.last_search_context = ""     # Clear context so state_transitioner can't re-match
            return None  # Let LLM handle the new search
        
        pid = belief.selected_property_id
        result_text = await get_property_details(property_id=pid)
        belief.last_tool_called = "get_property_details"
        belief.active_intents.discard("resolved_by_description")  # ONE-SHOT: clear after use
        # Extract key data for future cost questions
        _extract_property_data(belief, result_text)
        return (
            ChatResponse(
                response=result_text,
                tools_called=["get_property_details"],
                confidence=0.99,
            ),
            ["get_property_details"],
            0.99,
            "pre-llm::resolved",
        )
    
    # Case 1b: Photo request for currently selected property
    if belief.selected_property_id:
        photo_kw = ["fotos", "foto", "imagenes", "imágenes", "imagen", "mostrame fotos", "ver fotos"]
        if any(kw in msg_lower for kw in photo_kw):
            # If the user also asked for details/info in the same message,
            # bail out to the LLM specialist so it can call both tools.
            detail_kw = ["detalles", "detalle", "info", "información", "informacion",
                         "datos", "características", "caracteristicas", "más info",
                         "mas info", "más detalles", "mas detalles", "más información"]
            if any(kw in msg_lower for kw in detail_kw):
                return None  # Let LLM specialist handle multi-tool request
            from app.tools.v2.get_property_images import get_property_images
            import json as _json
            result_text = await get_property_images(property_id=belief.selected_property_id)
            # get_property_images now returns JSON: {display_text, images, title}
            # Parse it so the response text is user-friendly and images are available
            try:
                parsed = _json.loads(result_text)
                display_text = parsed.get("display_text", result_text)
            except Exception:
                display_text = result_text
            belief.last_tool_called = "get_property_images"
            return (
                ChatResponse(
                    response=display_text,
                    tools_called=["get_property_images"],
                    confidence=0.99,
                ),
                belief,
                0.99,
                "pre-llm::photos",
            )
    
    # ── SCHEDULING: Let the LLM specialist handle ALL scheduling conversation ──
    # Only intercept for the final booking fast-path: all fields collected + confirmation message
    if "scheduling" in (belief.active_intents or set()):
        msg_lower = message.lower().strip()
        
        # Topic switch detection: if user is asking about something else, exit scheduling
        other_topics = re.search(
            r"\b(busco|quiero|necesito|buscando|me interesa|mostrame|pasame|listas?|propiedades|de nuevo|otra vez|buscar|volver|requisitos|garantía|precio)\b",
            msg_lower
        )
        if other_topics:
            _clear_scheduling_state(belief)
            clear_saved_state(session_id)
            return None  # Let normal routing handle the new request
        
        # Loop escape hatch: too many turns without completing
        if belief.scheduling_loop_count >= 5:
            _clear_scheduling_state(belief)
            clear_saved_state(session_id)
            return (
                ChatResponse(
                    response=(
                        "Disculpá, no pude completar el agendamiento. "
                        "Si querés, escribime con todos los datos juntos: "
                        "nombre, día, horario y el número de propiedad. "
                        "También podés llamarnos al +54 9 3755 123456. "
                        "¿Necesitás algo más mientras tanto?"
                    ),
                    tools_called=["schedule_visit"],
                    confidence=0.5,
                ),
                ["schedule_visit"], 0.5, "pre-llm::scheduling-escape",
            )
        
        # Fast-path: all fields collected and user is confirming
        confirm_kw = ["sí", "si", "dale", "perfecto", "ok", "genial", "me sirve", "confirmo"]
        if (belief.scheduling_name and belief.scheduling_phone and 
            belief.scheduling_day and belief.scheduling_time and
            any(kw in msg_lower for kw in confirm_kw)):
            result_text = await schedule_visit(
                property_id=belief.selected_property_id or 0,
                nombre=belief.scheduling_name,
                telefono=belief.scheduling_phone,
                dia=belief.scheduling_day,
                horario=belief.scheduling_time,
            )
            belief.last_tool_called = "schedule_visit"
            _clear_scheduling_state(belief)
            clear_saved_state(session_id)
            return (
                ChatResponse(
                    response=result_text,
                    tools_called=["schedule_visit"],
                    confidence=0.99,
                ),
                ["schedule_visit"],
                0.99,
                "pre-llm::scheduled",
            )
    
    # Case 3: Cost question with known property data → respond from memory
    # BUT: don't intercept FAQ/ambiguous intents — let S1/S2 handle them
    if belief.selected_property_id and belief.last_property_data:
        cost_kw = ["cuanto", "cuánto", "precio", "cuesta", "sale",
                    "valor", "mensual"]
        faq_kw = ["requisitos", "garantía", "garantia", "contrato", "documentos",
                   "papeles", "mascotas", "qué necesito", "que necesito",
                   "qué piden", "que piden", "cómo es", "como es",
                   "cuáles son", "cuales son", "me pedirían", "me pedirian",
                   "cubre", "servicios", "incluye", "se pagaría",
                   "va por separado", "se paga aparte", "está incluido",
                   "ingresar", "entrar"]
        if any(kw in msg_lower for kw in cost_kw) and not any(kw in msg_lower for kw in faq_kw):
            response_text = (
                f"Según los datos de la propiedad #{belief.selected_property_id} "
                f"que vimos: {belief.last_property_data}\n\n"
                "¿Querés que te busque info más específica sobre requisitos o forma de pago?"
            )
            return (
                ChatResponse(
                    response=response_text,
                    tools_called=[],
                    confidence=0.95,
                ),
                [],
                0.95,
                "pre-llm::cost-data",
            )
    
    return None


async def route_message(
    message: str, session_id: str, phone: str = ""
) -> tuple[ChatResponse, ConversationBeliefState, str, float]:
    """Route message through S1 → Coordinator with memory integration."""
    t0 = time.perf_counter()

    # ── Load belief state ─────────────────────────────────────
    belief = await load_working_memory(session_id)
    if belief is None:
        belief = get_belief(session_id)

    # ── Session staleness check: auto-reset if inactive too long ──
    # V1 had this reset; V2 was missing it. When a user comes back
    # after more than SESSION_INACTIVITY_TIMEOUT (30 min), the old
    # belief state (turn_count, zone, operation) is wiped so the next
    # message starts fresh. This mirrors the v1 real_estate_agent.py
    # behavior of resetting the state machine on stale sessions.
    if is_session_stale(belief):
        logger.info(
            f"[Router] ⏱️ Stale session detected for {session_id} — "
            f"turn_count={belief.turn_count}, last_updated={belief.last_updated_at:.0f}, "
            f"timeout={SESSION_INACTIVITY_TIMEOUT}s. Resetting to fresh state."
        )
        # Clear Redis so the old state isn't loaded on the next message
        await clear_working_memory(session_id)
        # Also clear the specialist persistence state
        clear_saved_state(session_id)
        # Start fresh
        belief = get_belief(session_id)

    # ── /ResetMemory command ──────────────────────────────────
    # If user sends exactly "/ResetMemory", clear all session state and restart fresh.
    if message.strip().lower() == "/resetmemory":
        logger.info(f"[Router] 🧹 /ResetMemory triggered for {session_id}")
        await clear_working_memory(session_id)
        clear_saved_state(session_id)
        return (
            ChatResponse(
                response="✅ Memoria reiniciada. ¿En qué puedo ayudarte?",
                tools_called=[],
                confidence=1.0,
            ),
            get_belief(session_id), "reset-memory", 0,
        )

    # ── Cross-session context ─────────────────────────────────
    cross_session_context = ""
    if phone and belief.turn_count == 0:
        greeting = await build_greeting_from_episodes(phone)
        if greeting:
            cross_session_context = greeting
        persona_ctx = await build_personalized_context(phone)
        if persona_ctx:
            cross_session_context += "\n\n" + persona_ctx

    belief = update_belief(belief, message)
    context_prompt = build_context_prompt(belief)
    if cross_session_context:
        context_prompt = cross_session_context + "\n\n" + context_prompt

    # ── Cross-turn specialist persistence ─────────────────────
    # If the scheduling specialist was active last turn, keep it active
    saved = get_saved_state(session_id)
    if saved and saved.active_specialist == "scheduling":
        # Check if user is switching topics away from scheduling
        topic_switch_kw = r"\b(busco|quiero|necesito|buscando|me interesa|mostrame|propiedades|lista|requisitos|garantía|precio|alquilar|comprar)\b"
        if not re.search(topic_switch_kw, message.lower().strip()):
            from app.agents.coordinator import _build_scheduling_context as _bsc, SPECIALISTS
            sched_context = _bsc(belief)
            full_context = sched_context + "\n" + (context_prompt or "")
            specialist = SPECIALISTS["scheduling"]
            result, _ = await coordinate(message, session_id, full_context)
            _update_belief_from_result(belief, result)
            latency = (time.perf_counter() - t0) * 1000
            
            # Track loop count for escape hatch
            if result.tools_called and "schedule_visit" in result.tools_called:
                belief.scheduling_loop_count = 0
                # Booking complete — clear scheduling mode entirely
                _clear_scheduling_state(belief)
                clear_saved_state(session_id)
            else:
                belief.scheduling_loop_count += 1
            
            await save_working_memory(belief)
            return (
                ChatResponse(
                    response=result.response,
                    tools_called=result.tools_called,
                    confidence=result.confidence,
                    messages=result.messages,
                ),
                belief, "specialist::scheduling-persist", round(latency, 2),
            )
        else:
            # Topic switch detected — exit scheduling mode
            _clear_scheduling_state(belief)
            clear_saved_state(session_id)

    # ── Pre-LLM interception: when system deterministically knows what to do ──
    shortcut = await _try_pre_llm_shortcut(belief, message, session_id, phone)
    if shortcut:
        resp, tools, conf, router_label = shortcut
        latency = (time.perf_counter() - t0) * 1000
        await save_working_memory(belief)
        return (resp, belief, router_label, round(latency, 2))

    # ── System 1: regex match ─────────────────────────────────
    pattern = match_pattern(message)

    if pattern and pattern.confidence >= S1_CONFIDENCE_THRESHOLD:
        belief.last_tool_called = pattern.name

        if not pattern.needs_llm:
            # If greeting matched but message contains search keywords, delegate to S2
            if pattern.name.startswith("greeting"):
                search_kw = r"\b(busco|quiero|necesito|buscando|estoy buscando|me interesa|alquilar|alquiler|venta|comprar|departamento|depto|casa|ph|terreno)\b"
                msg_lower = message.lower().strip()
                if re.search(search_kw, msg_lower):
                    # Override context: tell LLM to process the full request, not just greet
                    override_context = (
                        "⚠️ El usuario combinó un saludo con una consulta de propiedades. "
                        "Ya lo saludaste — AHORA respondé a su consulta de búsqueda. "
                        "Si el usuario no especificó alquiler o venta, mostrale TODAS las propiedades "
                        "disponibles (tanto en alquiler como en venta). NO preguntes alquiler/compra "
                        "a menos que sea ambiguo — si dice 'departamento disponible', buscá todo.\n\n"
                    )
                    full_context = override_context + (context_prompt or "")
                    multistep_result = await process_message_multistep(message, session_id, full_context)
                    s2_result = multistep_result
                    latency = (time.perf_counter() - t0) * 1000
                    _update_belief_from_result(belief, s2_result)
                    await save_working_memory(belief)
                    return (
                        ChatResponse(
                            response=s2_result.response,
                            tools_called=s2_result.tools_called,
                            confidence=max(pattern.confidence, s2_result.confidence),
                            messages=s2_result.messages,
                        ),
                        belief, "s1→search", round(latency, 2),
                    )
            response_text = format_response(pattern, message)
            latency = (time.perf_counter() - t0) * 1000

            if pattern.name.startswith("greeting") and cross_session_context:
                parts = cross_session_context.split(".")
                greeting_part = parts[0].strip() + "."
                response_text = greeting_part + "\n\n" + response_text

            await save_working_memory(belief)
            return (
                ChatResponse(response=response_text, tools_called=[], confidence=pattern.confidence),
                belief, "s1", round(latency, 2),
            )
        else:
            # S1 identified intent → route through coordinator (supports scheduling specialist)
            # Check if this is a scheduling-related pattern
            scheduling_s1 = pattern.name.startswith("scheduling")
            if scheduling_s1:
                from app.agents.coordinator import _build_scheduling_context as _bsc
                sched_context = _bsc(belief)
                full_context = sched_context + "\n" + (context_prompt or "")
                result, specialist_name = await coordinate(message, session_id, full_context)
                _update_belief_from_result(belief, result)
                save_specialist_state(session_id, "scheduling")
                if result.tools_called:
                    belief.last_tool_called = result.tools_called[-1]
            else:
                multistep_result = await process_message_multistep(message, session_id, context_prompt)
                result = multistep_result
                specialist_name = "search"
                _update_belief_from_result(belief, result)
            
            latency = (time.perf_counter() - t0) * 1000
            await save_working_memory(belief)
            return (
                ChatResponse(
                    response=result.response,
                    tools_called=result.tools_called,
                    confidence=max(pattern.confidence, result.confidence),
                    messages=result.messages,
                ),
                belief, f"s1→{specialist_name}", round(latency, 2),
            )

    # ── Coordinator: route through intent classification → specialist
    # Check if message implies scheduling intent
    from app.agents.coordinator import _build_scheduling_context as _bsc_fb, SPECIALISTS, classify_intent
    intent = classify_intent(message)
    
    if intent == "scheduling":
        sched_context = _bsc_fb(belief)
        full_context = sched_context + "\n" + (context_prompt or "")
        result, specialist_name = await coordinate(message, session_id, full_context)
        save_specialist_state(session_id, "scheduling")
        if result.tools_called:
            belief.last_tool_called = result.tools_called[-1]
    else:
        multistep_result = await process_message_multistep(message, session_id, context_prompt)
        result = multistep_result
        specialist_name = "search"
    
    latency = (time.perf_counter() - t0) * 1000
    _update_belief_from_result(belief, result)
    await save_working_memory(belief)

    return (
        ChatResponse(
            response=result.response,
            tools_called=result.tools_called,
            confidence=result.confidence,
            messages=result.messages,
        ),
        belief, specialist_name, round(latency, 2),
    )


def _update_belief_from_result(belief: ConversationBeliefState, result: AgentResponse) -> None:
    import re
    if result.tools_called:
        belief.last_tool_called = result.tools_called[-1]
        
        # Extract selected_property_id from ALL tool calls
        for tr in result.raw_tool_results:
            args = tr.get("arguments", {})
            pid = args.get("property_id")
            if pid and isinstance(pid, (int, float)) and int(pid) > 0:
                belief.selected_property_id = int(pid)
                break  # First property_id found wins
        
        if "search_properties" in result.tools_called:
            for tr in result.raw_tool_results:
                if tr.get("name") == "search_properties":
                    result_text = str(tr.get("result", ""))
                    if "Encontré" in result_text:
                        m = re.search(r"Encontré (\d+)", result_text)
                        if m:
                            belief.last_search_count = int(m.group(1))
                    ids = re.findall(r"\[(\d+)\]", result_text)
                    belief.last_search_ids = [int(x) for x in ids]
                    # Build a rich lookup string including type, price, and TITLE
                    # Format: "  [1] Departamento en Centro — Alquiler $85,000/mes\n       1 dorm | 45m² | Depto 2 amb céntrico"
                    result_lines = result_text.split("\n")
                    summaries = []
                    for i, line in enumerate(result_lines):
                        m = re.match(r"\s*\[(\d+)\]\s+(.+?)\s+—\s+(.+?)$", line)
                        if m:
                            pid = m.group(1)
                            type_zone = m.group(2).strip()  # "Departamento en Centro"
                            price_info = m.group(3).strip()  # "Alquiler $85,000/mes"
                            # Peek at next line for the title
                            title = ""
                            if i + 1 < len(result_lines):
                                next_line = result_lines[i + 1].strip()
                                # Format: "1 dormitorio | 45m² | Depto 2 ambientes céntrico"
                                parts = next_line.split("|")
                                if len(parts) >= 3:
                                    title = parts[-1].strip()  # Last part is the title
                                else:
                                    title = next_line
                            summary = f"[{pid}] {type_zone} ({price_info})"
                            if title:
                                summary += f" — {title}"
                            summaries.append(summary)
                    if summaries:
                        belief.last_search_context = " | ".join(summaries)

        if "get_property_details" in result.tools_called:
            # Track that we showed details for this property (to avoid redundant re-show)
            belief.last_shown_detail_id = belief.selected_property_id
            # Extract property summary from the raw tool result for context injection
            for tr in result.raw_tool_results:
                if tr.get("name") == "get_property_details":
                    result_text = str(tr.get("result", ""))
                    # Extract key lines: price, address, services
                    lines = result_text.split("\n")
                    key_lines = [l.strip() for l in lines if any(
                        kw in l.lower() for kw in ["$", "córdoba", "san martín", "misiones", "servicios", "electricidad", "agua", "gas", "internet", "dormitorio", "m²"]
                    )][:5]
                    if key_lines:
                        belief.last_property_data = " | ".join(key_lines)[:300]

        if "schedule_visit" in result.tools_called:
            # Extract property ID from the response if not already set
            # LLM often says "la propiedad [7]" in scheduling context
            if not belief.selected_property_id:
                response_text = result.response.lower()
                prop_m = re.search(r"propiedad\s*(?:#|n[úu]mero|nro)?\s*\[?(\d+)\]?", response_text)
                if prop_m:
                    belief.selected_property_id = int(prop_m.group(1))
