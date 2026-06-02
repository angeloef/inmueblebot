"""Dual router — S1 + Coordinator (multi-agent Phase 8)."""

import asyncio
import re
import time

from loguru import logger

from app.agents.schemas import CSAgentResponse as AgentResponse, ChatResponse
from app.core.belief_state import (
    ConversationBeliefState,
    get_belief,
    is_session_stale,
    SESSION_INACTIVITY_TIMEOUT,
    soft_reset,
)
from app.core.context_aggregator import build_context_prompt
from app.core.state_transitioner import update_belief
from app.memory.working import save_working_memory, load_working_memory, clear_working_memory
from app.memory.episodic import build_greeting_from_episodes
from app.memory.user_model import build_personalized_context
from app.routers.system1 import format_response, match_pattern
from app.agents.s2_agent import process_message, process_message_multistep
from app.agents.coordinator import (
    coordinate,
    _build_scheduling_context,
    classify_intent_with_context,
    is_inmobiliaria_visit,
    get_inmobiliaria_location,
)
from app.core.state_transitioner import (
    extract_scheduling_name_llm,
    NAME_REASK_SIGNAL,
)
from app.agents.conversation_manager import (
    save_specialist_state,
    get_saved_state,
    clear_saved_state,
)

# ── Per-session async locks to prevent concurrent message races ───────────────
_session_locks: dict[str, asyncio.Lock] = {}


def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]

S1_CONFIDENCE_THRESHOLD = 0.70

_OUT_OF_SCOPE_RESPONSE = (
    "Soy un asistente inmobiliario especializado en propiedades en Oberá, Misiones. "
    "Puedo ayudarte a buscar casas, departamentos, terrenos o PH en alquiler o venta. "
    "¿En qué querés que te ayude?"
)

# ── Out-of-scope keyword patterns ──────────────────────────────────
# If a message contains ANY of these AND does NOT contain any real
# estate keywords, it's treated as off-topic. This prevents the bot
# from engaging with dating advice, recipes, jokes, spam, etc.
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
    # Generic: message is clearly not about real estate
    # Triggered only when NO real estate keywords are present
]

# Real estate keywords — if ANY are present, bypass out-of-scope check
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

def _is_out_of_scope(message: str) -> bool:
    """Check if message is clearly not a real estate request.

    Returns True if the message matches off-topic patterns AND has
    no real estate keywords. This prevents the bot from engaging with
    spam, dating advice, recipes, chitchat, etc.
    """
    msg_lower = message.lower().strip()

    # If any real estate keyword is present, it's in scope
    if any(kw in msg_lower for kw in _IN_SCOPE_KEYWORDS):
        return False

    # Check against out-of-scope patterns
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, msg_lower):
            return True

    return False


# ── Schema v4 helpers ──────────────────────────────────────────────

# Off-domain emergencies → immediate human handoff regardless of state.
_EMERGENCY = re.compile(
    r"\b(luz cortada|sin luz|corte de luz|ascensor|atrapad[oa]|inundaci[oó]n|"
    r"se inund|p[ée]rdida de agua|fuga de gas|olor a gas|escape de gas|robo|"
    r"me robaron|emergencia|accidente|ayuda urgente|incendio|fuego|"
    r"se prende fuego|me electrocut)\b",
    re.IGNORECASE,
)

# Hard topic switches that should EXIT an awaiting flow.
_HARD_TOPIC_SWITCH = re.compile(
    r"\b(busco|buscar|quiero ver|mostrame|otra propiedad|otra cosa|"
    r"chau|adi[oó]s|hasta luego|gracias adi[oó]s|cancelar|dejalo|olvidalo|"
    r"nada|mejor no|otra zona|comprar|alquilar otra)\b",
    re.IGNORECASE,
)

# Confirmation keywords.
_CONFIRM_KW = re.compile(
    r"\b(s[íi]|si|dale|perfecto|ok|okey|genial|listo|confirmo|confirm[aá]|"
    r"de una|joya|b[áa]rbaro|buen[ií]simo|me sirve|de acuerdo|correcto)\b",
    re.IGNORECASE,
)
_NEGATIVE_KW = re.compile(
    r"\b(no|nop|nope|para nada|cancel[aá]|mejor no|olvidalo|dejalo|no gracias)\b",
    re.IGNORECASE,
)

# Markers that indicate the bot failed / escalated / did not help.
_FAILURE_MARKERS = (
    "no estoy seguro de entenderte",
    "no me quedó del todo claro",
    "no pude entender",
    "no pude completar",
    "disculpá, ¿me",
    "quiero ayudarte bien",
    "te estoy conectando",
)


def _is_emergency(message: str) -> bool:
    return bool(_EMERGENCY.search(message or ""))


def _is_hard_topic_switch(message: str) -> bool:
    return bool(_HARD_TOPIC_SWITCH.search(message or ""))


def _is_confirmation(message: str) -> bool:
    msg = (message or "").lower().strip()
    if _NEGATIVE_KW.search(msg):
        return False
    return bool(_CONFIRM_KW.search(msg))


def _is_negative(message: str) -> bool:
    return bool(_NEGATIVE_KW.search((message or "").lower().strip()))


def _is_failed_response(response: str) -> bool:
    """True if the bot response looks like a non-help / escalation."""
    low = (response or "").lower()
    return any(m in low for m in _FAILURE_MARKERS)


def _detect_awaiting(response: str, belief) -> "str | None":
    """Infer which slot the bot is now waiting for, from its own response text."""
    low = (response or "").lower()
    is_question = "?" in response or "¿" in response
    if not is_question:
        return None
    if ("confirm" in low and "visita" in low) or "respondé sí" in low or "responde sí" in low:
        return "scheduling_confirm"
    if "nombre" in low:
        return "scheduling_name"
    if "qué día" in low or "que dia" in low or "qué fecha" in low or "cuándo" in low:
        return "scheduling_day"
    if "horario" in low or "a qué hora" in low or "a que hora" in low or "qué hora" in low:
        return "scheduling_time"
    return None


def _strip_messages(raw: list) -> list:
    """Reduce MemoryManager message dicts to {role, content} for the LLM API."""
    out = []
    for m in (raw or []):
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


async def _finalize_turn(belief, session_id: str, response_text: str) -> None:
    """Set last_bot_message, detect awaiting from response, update consecutive_failures."""
    belief.last_bot_message = response_text
    detected = _detect_awaiting(response_text, belief)
    if detected is not None:
        belief.awaiting = detected
    if _is_failed_response(response_text):
        belief.consecutive_failures += 1
    else:
        belief.consecutive_failures = 0


async def _finalize_and_check_handoff(
    belief, session_id: str, response_text: str, tools_called: list
) -> "tuple[str, list] | None":
    """Run _finalize_turn, then escalate to human after 3 consecutive failures.
    Returns (new_response, new_tools) if handoff replaces the response, else None.
    """
    await _finalize_turn(belief, session_id, response_text)
    if belief.consecutive_failures >= 3:
        try:
            from app.tools.v2.request_human_assistance import request_human_assistance as _rha
            handoff = await _rha(reason="3_failed_turns", message="")
        except Exception:
            handoff = "Te comunico con un asesor para ayudarte mejor."
        belief.consecutive_failures = 0
        belief.awaiting = None
        belief.last_bot_message = handoff
        return handoff, ["request_human_assistance"]
    return None


async def check_active_appointment(session_id: str) -> "str | None":
    """Return a description of the user's existing upcoming visit, or None."""
    try:
        from app.services.appointment_service import appointment_service
        from app.db.session import async_session_factory
        async with async_session_factory() as db:
            appts = await appointment_service.get_user_appointments_by_session(session_id, upcoming=True, db=db)
        if not appts:
            return None
        appts = sorted(appts, key=lambda a: a.start_time)
        a = appts[0]
        return f"{a.start_time.strftime('%A %d/%m a las %H:%M')}"
    except Exception:
        return None


async def _maybe_confirm_or_pass(belief, result, session_id: str) -> "tuple[str, str]":
    """If all scheduling fields present and not yet confirming, inject confirm step."""
    if result.tools_called and "schedule_visit" in result.tools_called:
        return result.response, "scheduling::booked"
    have_all = bool(
        getattr(belief, "scheduling_name", None)
        and getattr(belief, "scheduling_day", None)
        and getattr(belief, "scheduling_time", None)
        and getattr(belief, "selected_property_id", None)
    )
    if have_all and getattr(belief, "awaiting", None) != "scheduling_confirm":
        belief.awaiting = "scheduling_confirm"
        confirm = (
            f"¿Confirmo la visita para el {belief.scheduling_day} a las "
            f"{belief.scheduling_time} a nombre de {belief.scheduling_name}? "
            "Respondé Sí para confirmar."
        )
        belief.last_bot_message = confirm
        return confirm, "scheduling::confirm-request"
    return result.response, "scheduling::collecting"


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


def _summarize_tool_result(tool_name: str, args: dict, result: str) -> str:
    """Produce a compact one-line summary of a tool call result for the action log."""
    if tool_name == "search_properties":
        ids_match = re.findall(r"\[(\d+)\]", result)
        count = len(ids_match)
        ids_str = ", ".join(ids_match[:6])  # cap at 6 IDs
        tipo = args.get("tipo") or args.get("property_type") or ""
        zona = args.get("zona") or args.get("zone") or ""
        filters = ", ".join(x for x in [tipo, zona] if x)
        if count == 0:
            return f"0 resultados ({filters})"
        return f"{count} props ({filters}) → [{ids_str}]"
    elif tool_name in ("get_property_details", "get_property_images"):
        pid = args.get("property_id") or args.get("id") or "?"
        action = "detalles" if tool_name == "get_property_details" else "fotos"
        return f"{action} de prop #{pid} enviados"
    elif tool_name == "schedule_visit":
        pid = args.get("property_id") or "?"
        dia = args.get("dia") or args.get("day") or "?"
        return f"visita agendada prop #{pid} día={dia}"
    elif tool_name in ("cancel_appointment", "reschedule_appointment"):
        return result[:80] if result else tool_name
    elif tool_name == "get_faq_answer":
        return "FAQ respondida"
    elif tool_name == "request_human_assistance":
        return "derivado a humano"
    else:
        return result[:60] if result else tool_name


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
            # Bail to LLM if the message also asks for something else.
            # The LLM specialist handles multi-tool requests (details+photos,
            # photos+scheduling, etc.) while the shortcut only does pure photos.
            _other_intent_kw = [
                "detalles", "detalle", "info", "información", "informacion",
                "datos", "características", "caracteristicas",
                "agendar", "visita", "visitar", "coordinar", "cita",
                "conocer", "ir a ver", "cuándo", "cuando", "horario",
                "comparar", "compará", "compara",
                "busco", "buscando", "buscar", "mostrame", "listame",
                "pasame", "decime", "contame",
            ]
            if any(kw in msg_lower for kw in _other_intent_kw):
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
            await clear_saved_state(session_id)
            return None  # Let normal routing handle the new request
        
        # Loop escape hatch: too many turns without completing
        if getattr(belief, "scheduling_loop_count", 0) >= 5:
            _clear_scheduling_state(belief)
            belief.awaiting = None
            await clear_saved_state(session_id)
            try:
                from app.tools.v2.request_human_assistance import request_human_assistance as _rha
                handoff = await _rha(reason="scheduling_loop", message="")
            except Exception:
                handoff = "Te comunico con un asesor para ayudarte a coordinar la visita."
            belief.last_bot_message = handoff
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=handoff, tools_called=["request_human_assistance"], confidence=0.6),
                belief, "pre-llm::scheduling-escape-handoff", 0,
            )
        
        # Fast-path: all fields collected and user is confirming
        confirm_kw = ["sí", "si", "dale", "perfecto", "ok", "genial", "me sirve", "confirmo"]
        # Identity comes from the session (BSUID/phone), so the phone is no longer a
        # required field — only name + day + time gate the fast-path booking.
        # Schema v4: also require awaiting == "scheduling_confirm" so we don't skip the confirmation gate.
        if (getattr(belief, "awaiting", None) == "scheduling_confirm"
            and belief.scheduling_name and
            belief.scheduling_day and belief.scheduling_time and
            any(kw in msg_lower for kw in confirm_kw)):
            result_text = await schedule_visit(
                property_id=belief.selected_property_id or 0,
                nombre=belief.scheduling_name,
                telefono=belief.scheduling_phone,  # contact only — not identity
                dia=belief.scheduling_day,
                horario=belief.scheduling_time,
            )
            belief.last_tool_called = "schedule_visit"
            _clear_scheduling_state(belief)
            await clear_saved_state(session_id)
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
    async with _get_session_lock(session_id):
        return await _route_message_inner(message, session_id, phone)


async def _route_message_inner(
    message: str, session_id: str, phone: str = ""
) -> tuple[ChatResponse, ConversationBeliefState, str, float]:
    """Inner route_message implementation (runs under session lock)."""
    t0 = time.perf_counter()

    # ── Load belief state ─────────────────────────────────────
    belief = await load_working_memory(session_id)
    if belief is None:
        belief = get_belief(session_id)

    # ── Session staleness check: soft-reset volatile fields if inactive too long ──
    # When a user comes back after more than SESSION_INACTIVITY_TIMEOUT (12h),
    # volatile fields (active_intents, pending_offer, scheduling state) are cleared
    # while durable criteria (operation, type, zone, budget) are preserved.
    if is_session_stale(belief):
        logger.info(
            f"[Router] Stale session detected for {session_id} — "
            f"turn_count={belief.turn_count}, last_updated={belief.last_updated_at:.0f}, "
            f"timeout={SESSION_INACTIVITY_TIMEOUT}s. Applying soft reset."
        )
        belief = soft_reset(belief)
        # Clear the specialist persistence state (volatile)
        await clear_saved_state(session_id)
        # Clear short-term memory
        try:
            from app.core.memory import MemoryManager
            mm = MemoryManager()
            await mm.clear_short_term_memory(session_id)
        except Exception:
            pass

    # ── /ResetMemory command ──────────────────────────────────
    # If user sends exactly "/ResetMemory", clear all session state and restart fresh.
    if message.strip().lower() == "/resetmemory":
        logger.info(f"[Router] /ResetMemory triggered for {session_id}")
        await clear_working_memory(session_id)
        await clear_saved_state(session_id)
        return (
            ChatResponse(
                response="✅ Memoria reiniciada. ¿En qué puedo ayudarte?",
                tools_called=[],
                confidence=1.0,
            ),
            get_belief(session_id), "reset-memory", 0,
        )

    # ── Off-domain emergency detection (schema v4) ────────────
    if _is_emergency(message):
        logger.info(f"[Router] Emergency handoff for {session_id}: {message[:80]}")
        try:
            from app.tools.v2.request_human_assistance import request_human_assistance as _rha
            handoff = await _rha(reason="emergencia", message=message)
        except Exception:
            handoff = "Te comunico con un asesor de inmediato."
        belief.consecutive_failures = 0
        belief.awaiting = None
        belief.last_bot_message = handoff
        await save_working_memory(belief)
        return (
            ChatResponse(response=handoff, tools_called=["request_human_assistance"], confidence=1.0),
            belief, "emergency-handoff", 0,
        )

    # ── Out-of-scope guard ────────────────────────────────────
    # Detect clearly non-real-estate requests and redirect politely.
    # This runs BEFORE any S1 patterns so the bot never engages with
    # off-topic content (dating advice, recipes, jokes, chitchat, etc.)
    if _is_out_of_scope(message):
        logger.info(f"[Router] 🚫 Out-of-scope blocked for {session_id}: {message[:80]}")
        return (
            ChatResponse(
                response=_OUT_OF_SCOPE_RESPONSE,
                tools_called=[],
                confidence=1.0,
            ),
            belief, "out-of-scope", 0,
        )

    # ── Cross-session context ─────────────────────────────────
    cross_session_context = ""
    canonical_id = session_id or phone
    if canonical_id and belief.turn_count == 0:
        greeting = await build_greeting_from_episodes(canonical_id)
        if greeting:
            cross_session_context = greeting
        persona_ctx = await build_personalized_context(canonical_id)
        if persona_ctx:
            cross_session_context += "\n\n" + persona_ctx

    belief = update_belief(belief, message)
    context_prompt = build_context_prompt(belief)
    if cross_session_context:
        context_prompt = cross_session_context + "\n\n" + context_prompt

    # ── Load recent conversation history for LLM anaphora resolution (schema v4) ──
    recent_messages: list = []
    try:
        from app.core.memory import MemoryManager
        _mm = MemoryManager()
        _raw = await _mm.get_recent_messages(session_id, limit=6)
        recent_messages = _strip_messages(_raw)
    except Exception as _e:
        logger.debug(f"[Router] could not load recent_messages: {_e}")
        recent_messages = []

    # ── AWAITING FAST-PATH (schema v4) ────────────────────────
    if getattr(belief, "awaiting", None) and belief.awaiting.startswith("scheduling_"):

        # B1. Hard topic switch → exit scheduling flow, fall through.
        if _is_hard_topic_switch(message):
            belief.awaiting = None
            _clear_scheduling_state(belief)
            await clear_saved_state(session_id)
            # Do NOT return — fall through to normal routing.

        # B2. Confirmation step.
        elif belief.awaiting == "scheduling_confirm":
            if _is_negative(message):
                _clear_scheduling_state(belief)
                belief.awaiting = None
                await clear_saved_state(session_id)
                resp = "Entendido, cancelé el agendamiento. ¿Hay algo más en lo que te pueda ayudar?"
                belief.last_bot_message = resp
                belief.consecutive_failures = 0
                await save_working_memory(belief)
                return (
                    ChatResponse(response=resp, tools_called=[], confidence=0.95),
                    belief, "awaiting::confirm-cancel", 0,
                )
            if _is_confirmation(message):
                existing = await check_active_appointment(session_id)
                if existing:
                    resp = (
                        f"Ya tenés una visita agendada: {existing}. "
                        "¿Querés cancelarla primero antes de agendar otra?"
                    )
                    belief.awaiting = None
                    belief.last_bot_message = resp
                    belief.consecutive_failures = 0
                    await save_working_memory(belief)
                    return (
                        ChatResponse(response=resp, tools_called=[], confidence=0.95),
                        belief, "awaiting::has-active-appt", 0,
                    )
                from app.tools.v2.schedule_visit import schedule_visit
                result_text = await schedule_visit(
                    property_id=getattr(belief, "selected_property_id", 0) or 0,
                    nombre=getattr(belief, "scheduling_name", ""),
                    telefono=getattr(belief, "scheduling_phone", ""),
                    dia=getattr(belief, "scheduling_day", ""),
                    horario=getattr(belief, "scheduling_time", ""),
                )
                belief.last_tool_called = "schedule_visit"
                _failed = any(m in result_text for m in (
                    "⚠️", "No pude", "Los domingos", "El horario de las",
                    "Tuve un problema", "fuera de", "está ocupado", "Faltan datos",
                ))
                if not _failed:
                    _clear_scheduling_state(belief)
                    belief.awaiting = None
                    belief.consecutive_failures = 0
                    await clear_saved_state(session_id)
                belief.last_bot_message = result_text
                await save_working_memory(belief)
                return (
                    ChatResponse(response=result_text, tools_called=["schedule_visit"], confidence=0.99),
                    belief, "awaiting::booked", 0,
                )
            # Neither confirm nor deny → re-anchor.
            resp = (
                f"¿Confirmo la visita para el {getattr(belief, 'scheduling_day', '?')} a las "
                f"{getattr(belief, 'scheduling_time', '?')} a nombre de "
                f"{getattr(belief, 'scheduling_name', '?')}? "
                "Respondé Sí para confirmar o No para cambiar algo."
            )
            belief.last_bot_message = resp
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.9),
                belief, "awaiting::confirm-reask", 0,
            )

        # B3. Mid-flow interruption: user asks a question (not a topic switch).
        elif "?" in message or "¿" in message:
            from app.agents.s2_agent import process_message_with_specialist
            from app.agents.coordinator import SPECIALISTS
            answer = await process_message_with_specialist(
                message=message,
                session_id=session_id,
                context_prompt=context_prompt,
                specialist=SPECIALISTS.get("knowledge"),
                recent_messages=recent_messages,
            )
            resp = answer.response + "\n\n¿Querés continuar con el agendamiento de la visita?"
            # Keep belief.awaiting unchanged.
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=getattr(answer, "tools_called", []),
                             confidence=getattr(answer, "confidence", 0.8)),
                belief, "awaiting::midflow-answer", 0,
            )

        # B4. scheduling_name slot with LLM/anaphora extraction.
        elif belief.awaiting == "scheduling_name":
            extracted = await extract_scheduling_name_llm(belief, message)
            if extracted == NAME_REASK_SIGNAL:
                resp = "Perfecto. ¿Me decís tu nombre completo para registrar la visita?"
                belief.awaiting = "scheduling_name"
                belief.last_bot_message = resp
                await save_working_memory(belief)
                return (
                    ChatResponse(response=resp, tools_called=[], confidence=0.9),
                    belief, "awaiting::name-reask", 0,
                )
            if extracted:
                belief.scheduling_name = extracted
            # Fall through to scheduling specialist for next slot.
            sched_context = _build_scheduling_context(belief) + "\n" + (context_prompt or "")
            result, _ = await coordinate(message, session_id, sched_context, recent_messages=recent_messages)
            await save_specialist_state(session_id, "scheduling")
            _update_belief_from_result(belief, result)
            await _finalize_turn(belief, session_id, result.response)
            resp_text, label = await _maybe_confirm_or_pass(belief, result, session_id)
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp_text, tools_called=getattr(result, "tools_called", []),
                             confidence=getattr(result, "confidence", 0.9)),
                belief, label, 0,
            )

        # B5. Any other scheduling_* slot (day / time).
        else:
            sched_context = _build_scheduling_context(belief) + "\n" + (context_prompt or "")
            result, _ = await coordinate(message, session_id, sched_context, recent_messages=recent_messages)
            await save_specialist_state(session_id, "scheduling")
            _update_belief_from_result(belief, result)
            await _finalize_turn(belief, session_id, result.response)
            resp_text, label = await _maybe_confirm_or_pass(belief, result, session_id)
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp_text, tools_called=getattr(result, "tools_called", []),
                             confidence=getattr(result, "confidence", 0.9)),
                belief, label, 0,
            )

    # ── Inmobiliaria-office visit: share location + hours, never book ──
    if is_inmobiliaria_visit(message):
        loc = await get_inmobiliaria_location()
        belief.awaiting = None
        belief.last_bot_message = loc
        belief.consecutive_failures = 0
        await save_working_memory(belief)
        return (
            ChatResponse(response=loc, tools_called=["get_faq_answer"], confidence=0.95),
            belief, "inmobiliaria-visit", 0,
        )

    # ── Cross-turn specialist persistence ─────────────────────
    # If the scheduling specialist was active last turn, keep it active
    saved = await get_saved_state(session_id)
    if saved and saved.active_specialist == "scheduling":
        # Check if user is switching topics away from scheduling
        topic_switch_kw = r"\b(busco|quiero|necesito|buscando|me interesa|mostrame|propiedades|lista|requisitos|garantía|precio|alquilar|comprar)\b"
        if not re.search(topic_switch_kw, message.lower().strip()):
            # Deterministic booking: if we already have name + day + time + property and
            # the user confirms, call schedule_visit directly with the belief fields.
            # The LLM specialist is unreliable assembling a date split across turns.
            _confirm = re.search(
                r"\b(si|s[íi]|dale|perfecto|ok|okay|genial|listo|confirmo|de una|joya|b[áa]rbaro|buenisimo|me sirve)\b",
                message.lower(),
            )
            if (_confirm and getattr(belief, "awaiting", None) == "scheduling_confirm"
                    and belief.scheduling_name and belief.scheduling_day
                    and belief.scheduling_time and belief.selected_property_id):
                from app.tools.v2.schedule_visit import schedule_visit as _sv
                _txt = await _sv(
                    property_id=belief.selected_property_id,
                    nombre=belief.scheduling_name,
                    dia=belief.scheduling_day,
                    horario=belief.scheduling_time,
                )
                belief.last_tool_called = "schedule_visit"
                _failed = any(m in _txt for m in ("⚠️", "No pude", "Los domingos", "El horario de las", "Tuve un problema", "fuera de"))
                if not _failed:
                    _clear_scheduling_state(belief)
                    await clear_saved_state(session_id)
                await save_working_memory(belief)
                latency = (time.perf_counter() - t0) * 1000
                return (
                    ChatResponse(response=_txt, tools_called=["schedule_visit"], confidence=0.95),
                    belief, "specialist::sched-deterministic", round(latency, 2),
                )
            from app.agents.coordinator import _build_scheduling_context as _bsc, SPECIALISTS
            sched_context = _bsc(belief)
            full_context = sched_context + "\n" + (context_prompt or "")
            specialist = SPECIALISTS["scheduling"]
            result, _ = await coordinate(message, session_id, full_context, recent_messages=recent_messages)
            _update_belief_from_result(belief, result)
            latency = (time.perf_counter() - t0) * 1000
            
            # Track loop count for escape hatch
            if result.tools_called and "schedule_visit" in result.tools_called:
                belief.scheduling_loop_count = 0
                # Booking complete — clear scheduling mode entirely
                _clear_scheduling_state(belief)
                await clear_saved_state(session_id)
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
            await clear_saved_state(session_id)

    # ── Pre-LLM interception: when system deterministically knows what to do ──
    shortcut = await _try_pre_llm_shortcut(belief, message, session_id, phone)
    if shortcut:
        resp, tools, conf, router_label = shortcut
        latency = (time.perf_counter() - t0) * 1000
        await save_working_memory(belief)
        return (resp, belief, router_label, round(latency, 2))

    # ── System 1: regex match ─────────────────────────────────
    pattern = match_pattern(message, belief)

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
                    multistep_result = await process_message_multistep(message, session_id, full_context, recent_messages=recent_messages)
                    s2_result = multistep_result
                    latency = (time.perf_counter() - t0) * 1000
                    _update_belief_from_result(belief, s2_result)
                    _resp_text = s2_result.response
                    _resp_tools = s2_result.tools_called
                    _handoff = await _finalize_and_check_handoff(belief, session_id, _resp_text, _resp_tools)
                    if _handoff:
                        _resp_text, _resp_tools = _handoff
                    await save_working_memory(belief)
                    return (
                        ChatResponse(
                            response=_resp_text,
                            tools_called=_resp_tools,
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

            # Static S1 (greetings/FAQ): track last_bot_message but don't count as failure.
            await _finalize_turn(belief, session_id, response_text)
            belief.consecutive_failures = 0  # static canned replies are never failures
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
                result, specialist_name = await coordinate(message, session_id, full_context, recent_messages=recent_messages)
                _update_belief_from_result(belief, result)
                await save_specialist_state(session_id, "scheduling")
                if result.tools_called:
                    belief.last_tool_called = result.tools_called[-1]
            else:
                # Secondary scheduling check: messages like "lo quiero ver el sabado a las 11"
                # arrive via S1 property-selection path but need the scheduling specialist,
                # not generic multistep (which has no scheduling context and confuses day names).
                _visit_kw = re.search(
                    r"\b(quiero ver|ir a ver|visitarlo|visitarla|coordinar|agendar)\b",
                    message.lower(),
                )
                _day_kw = re.search(
                    r"\b(hoy|ma[nñ]ana|martes|mi[eé]rcoles|jueves|viernes|lunes|s[aá]bado|domingo)\b",
                    message.lower(),
                )
                if _visit_kw and _day_kw:
                    from app.agents.coordinator import _build_scheduling_context as _bsc2
                    sched_context = _bsc2(belief)
                    full_context = sched_context + "\n" + (context_prompt or "")
                    result, specialist_name = await coordinate(message, session_id, full_context, recent_messages=recent_messages)
                    _update_belief_from_result(belief, result)
                    await save_specialist_state(session_id, "scheduling")
                    if result.tools_called:
                        belief.last_tool_called = result.tools_called[-1]
                else:
                    multistep_result = await process_message_multistep(message, session_id, context_prompt, recent_messages=recent_messages)
                    result = multistep_result
                    specialist_name = "search"
                    _update_belief_from_result(belief, result)

            latency = (time.perf_counter() - t0) * 1000
            _resp_text = result.response
            _resp_tools = result.tools_called
            _handoff = await _finalize_and_check_handoff(belief, session_id, _resp_text, _resp_tools)
            if _handoff:
                _resp_text, _resp_tools = _handoff
            await save_working_memory(belief)
            return (
                ChatResponse(
                    response=_resp_text,
                    tools_called=_resp_tools,
                    confidence=max(pattern.confidence, result.confidence),
                    messages=result.messages,
                ),
                belief, f"s1→{specialist_name}", round(latency, 2),
            )

    # ── Coordinator: route through intent classification → specialist
    # Check if message implies scheduling intent
    from app.agents.coordinator import _build_scheduling_context as _bsc_fb, SPECIALISTS
    intent = await classify_intent_with_context(message, belief, recent_messages)

    if intent == "scheduling":
        sched_context = _bsc_fb(belief)
        full_context = sched_context + "\n" + (context_prompt or "")
        result, specialist_name = await coordinate(message, session_id, full_context, recent_messages=recent_messages)
        if result.tools_called:
            belief.last_tool_called = result.tools_called[-1]
        # After a successful booking, clear scheduling state so the next turn doesn't
        # re-enter the scheduling loop (e.g. "me confirmas" should check appointments,
        # not try to book again). On failure/partial, keep state for the next turn.
        if "schedule_visit" in (result.tools_called or []):
            _failed = any(m in result.response for m in (
                "⚠️", "No pude", "Los domingos", "El horario de las",
                "Tuve un problema", "fuera de", "está ocupado", "Faltan datos",
            ))
            if not _failed:
                _clear_scheduling_state(belief)
                await clear_saved_state(session_id)
            else:
                await save_specialist_state(session_id, "scheduling")
        else:
            await save_specialist_state(session_id, "scheduling")
    else:
        multistep_result = await process_message_multistep(message, session_id, context_prompt, recent_messages=recent_messages)
        result = multistep_result
        specialist_name = "search"
    
    latency = (time.perf_counter() - t0) * 1000
    _update_belief_from_result(belief, result)
    _resp_text = result.response
    _resp_tools = result.tools_called
    _handoff = await _finalize_and_check_handoff(belief, session_id, _resp_text, _resp_tools)
    if _handoff:
        _resp_text, _resp_tools = _handoff
    await save_working_memory(belief)

    return (
        ChatResponse(
            response=_resp_text,
            tools_called=_resp_tools,
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

                    # Zero-result zone fallback: when the zone-filtered search returns nothing,
                    # clear the zone so the *next* turn searches broadly, and set a pending_offer
                    # so the context tells the LLM exactly what to do when the user confirms.
                    if not belief.last_search_ids and belief.zone:
                        cleared_zone = belief.zone
                        belief.zone = None
                        belief.pending_offer = (
                            f"mostrar {belief.property_type or 'propiedades'} "
                            + (f"de {belief.operation} " if belief.operation else "")
                            + f"disponibles en otras zonas (no hay resultados en {cleared_zone})"
                            + " — llamar search_properties sin parámetro zona"
                        )
                    elif belief.last_search_ids:
                        # Results found — clear any stale zone-fallback offer
                        belief.pending_offer = None

                    # Populate search_history
                    if belief.last_search_ids:
                        criteria = {}
                        if belief.operation:
                            criteria["operation"] = belief.operation
                        if belief.property_type:
                            criteria["tipo"] = belief.property_type
                        if belief.zone:
                            criteria["zona"] = belief.zone
                        if belief.bedrooms_min is not None:
                            criteria["dormitorios"] = belief.bedrooms_min
                        if belief.budget_max is not None:
                            criteria["presupuesto_max"] = belief.budget_max
                        belief.search_history.append({
                            "criteria": criteria,
                            "ids": list(belief.last_search_ids),
                            "context": belief.last_search_context,
                            "count": belief.last_search_count,
                        })
                        if len(belief.search_history) > 3:
                            belief.search_history.pop(0)

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

    # ── Append to tool call log ──
    from app.core.config import get_settings
    _settings = get_settings()
    for tr in (result.raw_tool_results or []):
        tool_name = tr.get("name", "")
        tool_args = tr.get("arguments", {})
        tool_result_str = str(tr.get("result", ""))

        # Compact args representation (only key fields)
        key_arg_fields = ["property_id", "tipo", "zona", "operation", "operacion",
                          "dia", "horario", "nombre", "query"]
        args_compact = ", ".join(
            f"{k}={v}" for k, v in tool_args.items()
            if k in key_arg_fields and v is not None
        )

        summary = _summarize_tool_result(tool_name, tool_args, tool_result_str)

        entry = {
            "turn": belief.turn_count,
            "tool": tool_name,
            "args": args_compact,
            "result": summary,
        }
        belief.tool_call_log.append(entry)

    # Trim to max entries
    max_entries = getattr(_settings, "TOOL_LOG_MAX_ENTRIES", 5)
    if len(belief.tool_call_log) > max_entries:
        belief.tool_call_log = belief.tool_call_log[-max_entries:]


# ═══════════════════════════════════════════════════════════════════════
# WhatsApp Inbox — Conversation persistence wrapper
# ═══════════════════════════════════════════════════════════════════════
# Wraps route_message() to persist the turn to the database after
# every successful bot response.  v2_adapter.py calls this instead of
# route_message() directly.

from app.db.session import async_session_factory
from app.services.conversation_service import upsert_conversation, save_turn


async def route_message_with_persistence(
    message: str, session_id: str, phone: str = ""
) -> tuple:
    """Call route_message() and persist the turn to DB on success."""
    result = await route_message(message, session_id, phone)
    response, belief, router_label, latency_ms = result

    # Do NOT persist if the response is an error or the message is empty
    if not response or not response.response:
        return result

    try:
        async with async_session_factory() as db:
            conv_id = await upsert_conversation(db, session_id, phone=phone)
            await save_turn(
                db,
                conv_id,
                user_message=message,
                bot_response=response.response,
                tools_called=response.tools_called or [],
                router=router_label or "",
                latency_ms=latency_ms or 0,
                confidence=response.confidence or 0,
            )
    except Exception as e:
        logger.error(f"[Router] Failed to persist turn: {e}")

    return result
