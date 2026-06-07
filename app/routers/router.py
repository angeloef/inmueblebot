"""Dual router — S1 + Coordinator (multi-agent Phase 8)."""

import asyncio
import os
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
    extract_scheduling_day,
    extract_scheduling_time,
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

# Explicit request to talk to a real person → human handoff, top priority.
# Must outrank negotiator/search keyword routing (e.g. "todo caro, quiero hablar
# con una persona real" should escalate, not route to the price specialist).
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


def _is_human_request(message: str) -> bool:
    """True if the user explicitly asks to talk to a real person/agent."""
    return bool(_HUMAN_REQUEST.search(message or ""))


def _is_hard_topic_switch(message: str) -> bool:
    return bool(_HARD_TOPIC_SWITCH.search(message or ""))


# Photo / detail intents — a refinement must not hijack these.
_PHOTO_DETAIL_INTENT = re.compile(
    r"\b(fotos?|im[aá]gen(?:es)?|detalles?|informaci[oó]n|caracter[ií]sticas)\b",
    re.IGNORECASE,
)
# Scheduling verbs that indicate the user wants to book, not refine a search.
_SCHEDULING_VERB = re.compile(
    r"\b(agendar|agend[aá]|visita|visitar|coordinar|coordin[aá]|turno|cita|reservar)\b",
    re.IGNORECASE,
)

# "I want to see it in person" phrases that signal visit intent without a scheduling verb.
_VISIT_PHRASE = re.compile(
    r"\b(en persona|ir a verl[oa]|quiero verl[oa]|quisiera verl[oa]|"
    r"me gustar[ií]a verl[oa]|visitarl[oa]|conocerl[oa]|ir a conocerl[oa])\b",
    re.IGNORECASE,
)

# Preference/selection reference to a property TYPE among the ones the user already
# viewed ("me interesa más la casa", "prefiero el departamento"). Group 1 = the type.
_PREFERENCE_REF = re.compile(
    r"\b(?:me\s+interesa|me\s+gusta|prefiero|me\s+quedo\s+con|me\s+inclino|me\s+convence|"
    r"elijo|eleg[ií]|me\s+encanta|me\s+gust[oó])\b[^.?!]*?\b(?:la|el|esa|ese|esta|este)\s+"
    r"(casa|departamento|depto|monoambiente|ph|terreno|propiedad)\b",
    re.IGNORECASE,
)


# A bare money amount ("tengo 35 millones", "200 mil") — budget without a prefix.
_BARE_AMOUNT = re.compile(r"\b\d[\d.,]*\s*(?:mil|millones|mill[oó]n|lucas|palos|k)\b", re.IGNORECASE)


def _message_has_search_criteria(message: str) -> bool:
    """True if the message carries at least one property search criterion
    (budget, bedrooms, zone, type, or operation)."""
    from app.core.state_transitioner import (
        BUDGET_PATTERN, BEDROOMS_PATTERN, ZONE_PATTERNS, TYPE_PATTERNS, OPERATION_PATTERNS,
    )
    low = (message or "").lower()
    if BUDGET_PATTERN.search(low) or BEDROOMS_PATTERN.search(low) or _BARE_AMOUNT.search(low):
        return True
    for pattern, _ in (ZONE_PATTERNS + TYPE_PATTERNS + OPERATION_PATTERNS):
        if re.search(pattern, low):
            return True
    return False


def _is_search_refinement(belief, message: str) -> bool:
    """True if the message refines an existing search (new criteria, no scheduling).

    Guards against the spurious-scheduling bug: after a search, messages like
    "2 ambientes, zona centro" or "tengo 35 millones" must re-run the search,
    not get swallowed into the scheduling flow.
    """
    # Need a prior search to refine.
    if not getattr(belief, "last_search_ids", None):
        return False
    # Must carry NEW search criteria.
    if not _message_has_search_criteria(message):
        return False
    # Must NOT be a scheduling message (day/time/name/booking verb).
    from app.core.state_transitioner import DAY_PATTERN, TIME_PATTERN, NAME_PATTERN
    if _SCHEDULING_VERB.search(message):
        return False
    if DAY_PATTERN.search(message) or NAME_PATTERN.search(message):
        return False
    # Don't hijack photo/detail asks — those route normally.
    if _PHOTO_DETAIL_INTENT.search(message):
        return False
    # Don't hijack FAQ/knowledge questions — a question that merely mentions
    # "alquilar/comprar" (operation) is informational, not a new search.
    if _is_faq_question(message):
        return False
    return True


# ── FAQ / knowledge question detection ────────────────────────────────────────
# A message is an informational (FAQ) question — NOT a property-search refinement —
# when it carries a knowledge TOPIC (requisitos, garantía, contrato, documentación,
# seña, expensas, comisión, mascotas…) or a PROCESS question ("cómo es el tema para
# alquilar", "qué necesito para…"). This is used ONLY to ROUTE the turn to the
# knowledge specialist; the answer itself is composed by the LLM (get_faq_answer)
# with full conversation context — never assembled from regex.
_FAQ_TOPIC = re.compile(
    r"\b("
    r"requisitos?|garant[ií]as?|garante|fiador|aval|"
    r"recibos?\s+de\s+sueldo|comprobantes?\s+de\s+ingresos?|"
    r"documentaci[oó]n|papeles|documentos?|"
    r"contrato|escritura|boleto\s+de\s+compra|"
    r"se[ñn]a|dep[oó]sito|adelanto|expensas?|comisi[oó]n|honorarios?|"
    r"impuestos?|servicios?\s+(?:inclu|aparte|a\s+cargo)|mascotas?"
    r")\b",
    re.IGNORECASE,
)
_FAQ_PROCESS = re.compile(
    r"(c[oó]mo\s+(?:es|ser[ií]a|funciona|hago|tengo\s+que\s+hacer|"
    r"ser[ií]a\s+el\s+tema|es\s+el\s+tema|ingreso|hac[ée]s)|"
    r"qu[eé]\s+(?:necesito|piden|hace\s+falta|requisitos?|documentos?|papeles|"
    r"tengo\s+que\s+(?:hacer|presentar|llevar|tener))|"
    r"se\s+puede\s+(?:alquilar|comprar)\s+(?:con|sin)|"
    r"para\s+(?:alquilar|comprar|ingresar|entrar))",
    re.IGNORECASE,
)


def _count_questions(message: str) -> int:
    """Cheap count of DISTINCT questions in one message (number of '?' terminators,
    collapsing runs like '???'). A hint for whether to request a multi-bubble answer —
    the specialist LLM makes the final call on how to split."""
    if not message:
        return 0
    return len(re.findall(r"\?+", message))


def _is_faq_question(message: str) -> bool:
    """True if the message is an informational/FAQ question rather than a property
    search or scheduling action. Matches a knowledge topic OR a process question."""
    low = (message or "").lower()
    if _FAQ_TOPIC.search(low):
        return True
    if ("?" in message or "¿" in message) and _FAQ_PROCESS.search(low):
        return True
    return False


def _looks_like_scheduling_answer(message: str) -> bool:
    """True if a message (even one phrased as a question) is ANSWERING a scheduling
    slot — i.e. it carries a day or a time. Used so that slot answers like
    "a las 5 podría ser?" or "podría ser el martes que viene?" are captured by the
    slot fast-path instead of being mistaken for a mid-flow interruption (which would
    re-route to the knowledge specialist and append "¿Seguimos…?" without persisting
    the slot). FAQ/photo/detail interruptions are excluded."""
    low = (message or "").lower()
    # Genuine off-topic interruptions are NOT slot answers.
    if _is_faq_question(message):
        return False
    if re.search(r"\b(fotos?|im[aá]gen(?:es)?|detalles?)\b", low):
        return False
    from app.core.state_transitioner import DAY_PATTERN, TIME_PATTERN
    if DAY_PATTERN.search(low) or TIME_PATTERN.search(low):
        return True
    # Time-of-day phrase answering a time slot ("por la tarde", "a la mañana").
    if re.search(r"\b(?:a|de|por|en)\s+la\s+(?:ma[nñ]ana|tarde|noche)\b", low):
        return True
    return False


# ── Slot rejection / change ("ese día no puedo, otro día?") ──────────────────
# The user is rejecting or asking to change the day/time the bot just proposed.
# Distinct from a plain "no" (which cancels) and from a mid-flow question (B3) —
# so it must be handled BEFORE both: clear the rejected slot(s), capture any new
# slot bundled in the same message, and ask for what's still missing WITHOUT the
# repetitive "¿Seguimos con el agendamiento?" suffix.
_REJECT_DAY = re.compile(
    r"\b(no\s+puedo|no\s+(?:me\s+)?(?:viene|queda|sirve|conviene|va)|"
    r"ese\s+d[ií]a\s+no|es[ea]\s+fecha\s+no|otro\s+d[ií]a|otra\s+fecha|"
    r"cambiar?\s+(?:el\s+)?d[ií]a)\b",
    re.IGNORECASE,
)
_REJECT_TIME = re.compile(
    r"\b(esa\s+hora\s+no|a\s+esa\s+hora\s+no|otra\s+hora|otro\s+horario|"
    r"cambiar?\s+(?:el\s+)?horario|m[áa]s\s+(?:temprano|tarde))\b",
    re.IGNORECASE,
)


def _is_slot_change_request(message: str) -> bool:
    """True if the user is rejecting/changing the proposed scheduling slot."""
    return bool(_REJECT_DAY.search(message or "") or _REJECT_TIME.search(message or ""))


# ── Pure list-selection detection ("me interesa el 8") ────────────────────────
# Detects a message whose sole intent is to PICK one property from the last search
# list (by ID or ordinal). Used to auto-show that property's details instead of a
# generic teaser. Bundled intents (scheduling / photos / comparison / FAQ) are
# excluded so they keep their dedicated handling.
_SELECTION_RE = re.compile(
    r"(?:^|\b)(?:me\s+(?:interesa|gusta|quedo\s+con|inclino\s+por)|me\s+quedo\s+con|"
    r"quiero|dame|ver[ée]?|mostrame|elijo|prefiero|el|la|ese|esa|opci[oó]n|"
    r"n[uú]mero|nro|propiedad)\s+"
    r"(?:el|la|los|las|opci[oó]n|n[uú]mero|nro|propiedad|#)?\s*"
    r"(?:\d+|primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|[uú]ltim[oa])\b",
    re.IGNORECASE,
)
_SELECTION_EXCLUDE = re.compile(
    r"\b(agendar|agend[aá]|agendame|visita|visitar|coordinar|coordin[aá]|cita|turno|"
    r"fotos?|im[aá]gen(?:es)?|comparar|compar[aá]|versus|\bvs\b|"
    r"busco|buscando|buscar|otra\s+opci[oó]n|otras\s+opciones)\b",
    re.IGNORECASE,
)


def _is_pure_selection(message: str) -> bool:
    """True if the message just picks one listed property (no bundled scheduling,
    photos, comparison, FAQ or new search)."""
    low = (message or "").lower()
    if not _SELECTION_RE.search(low):
        return False
    if _SELECTION_EXCLUDE.search(low):
        return False
    if _is_faq_question(message):
        return False
    return True


# ── Too-broad search narrowing ────────────────────────────────────────────────
# When a search returns MORE than this many results, ask the user for ONE more
# missing criterion (zone, dorms, budget, …) before dumping the list, so the
# results match what they actually want. Repeats turn-by-turn until the list is
# small enough OR every criterion is already filled.
_NARROW_RESULT_THRESHOLD = 9

# Order in which we request a narrowing criterion (first still-missing one wins).
_NARROW_CRITERIA: list[tuple[str, str]] = [
    ("operation", "¿La buscás para alquilar o para comprar?"),
    ("property_type", "¿Qué tipo de propiedad te interesa? (departamento, casa, monoambiente, PH o terreno)"),
    ("zone", "¿En qué zona o barrio preferís? (por ejemplo Centro, UNAM, Barrio Schuster, Krause…)"),
    ("bedrooms_min", "¿Cuántos dormitorios necesitás como mínimo?"),
    ("budget_max", "¿Cuál es tu presupuesto máximo aproximado?"),
]


def _next_narrow_criterion(belief) -> "tuple[str, str] | None":
    """Return (field, question) for the next missing search criterion, or None if all set."""
    for field, question in _NARROW_CRITERIA:
        if getattr(belief, field, None) is None:
            return field, question
    return None


# Short natural-language hints for the "also tell me" secondary criterion.
_NARROW_FIELD_HINT: dict[str, str] = {
    "operation":     "si buscás alquilar o comprar",
    "property_type": "qué tipo de propiedad te interesa (departamento, casa, PH…)",
    "zone":          "la zona o barrio de tu preferencia",
    "bedrooms_min":  "cuántos dormitorios necesitás",
    "budget_max":    "tu presupuesto máximo aproximado",
}


def _maybe_narrow_search(belief) -> "tuple[str, str] | None":
    """If the last search was too broad AND criteria are still missing, return
    (question_text, fields_key) asking for up to TWO missing criteria in one message.

    `fields_key` is a comma-separated string of the belief attributes to collect
    (e.g. "zone" or "zone,bedrooms_min"). Set as ``belief.awaiting = f"search_narrow:{fields_key}"``.

    Returns None when the result set is ≤ threshold OR every criterion is filled.
    """
    count = len(getattr(belief, "last_search_ids", None) or [])
    if count <= _NARROW_RESULT_THRESHOLD:
        return None

    # Collect the next 1–2 still-missing criteria (in priority order).
    # Skip criteria the user explicitly said they don't care about (criteria_any),
    # e.g. zone after "cualquier zona mientras sea en Oberá".
    _criteria_any = getattr(belief, "criteria_any", None) or set()
    missing: list[tuple[str, str]] = []
    for field, question in _NARROW_CRITERIA:
        if getattr(belief, field, None) is None and field not in _criteria_any:
            missing.append((field, question))
        if len(missing) >= 2:
            break

    if not missing:
        return None  # everything specified — show the (still broad) list as-is

    field1, question1 = missing[0]

    if len(missing) == 1:
        # Single missing criterion — clean, focused question.
        text = (
            f"Encontré {count} opciones que coinciden 👍 Para mostrarte solo las que mejor "
            f"se ajustan a lo que buscás, {question1}"
        )
        return text, field1

    # Two criteria missing — ask for both so the user can answer one or both at once.
    field2, _ = missing[1]
    hint2 = _NARROW_FIELD_HINT.get(field2, field2)
    text = (
        f"Encontré {count} opciones que coinciden 👍 "
        f"Para ajustar mejor los resultados, {question1} "
        f"También podés indicarme {hint2} si ya lo tenés en mente."
    )
    return text, f"{field1},{field2}"


# "Show them anyway" signals — the user opts out of further narrowing.
_SHOW_ALL_ANYWAY = re.compile(
    r"\b(todos|todas|igual|no importa|me da igual|cualquiera|mostrame todo|"
    r"ver todas|las que sean|no s[eé]|no tengo preferencia)\b",
    re.IGNORECASE,
)

# Narrowing ESCAPE signals — the user is NOT answering the "which zone/dorms/budget?"
# question; they reference a property, ask for details/photos, want to schedule, or ask
# for something cheaper. In that case we must NOT swallow the message as a narrowing
# answer (which re-runs the same broad search and re-asks) — clear `awaiting` and fall
# through to normal routing (pronoun resolution, detail/photo handling, LLM specialist).
_NARROW_ESCAPE = re.compile(
    r"\b(fotos?|im[aá]gen(?:es)?|detalles?|informaci[oó]n|caracter[ií]sticas|"
    r"opci[oó]n|el primero|la primera|el segundo|la segunda|el tercero|la tercera|"
    r"primero|segundo|tercero|"
    r"agendar|agend[aá]|agendame|visita|visitar|coordinar|coordin[aá]|turno|cita|"
    r"m[aá]s\s+barat|m[aá]s\s+econ[oó]mic|m[aá]s\s+caro|m[aá]s\s+grande|m[aá]s\s+chico)\b",
    re.IGNORECASE,
)


def _capture_narrow_field(belief, field: str, message: str) -> bool:
    """Set the specific search criterion the bot asked for from the user's answer.

    update_belief() already ran this turn and may have set operation/type/zone when
    the words were present; this fills the gaps — notably BARE numeric answers like
    "2" (dorms) or "80000"/"80 mil" (budget) that the generic extractors skip.
    Returns True if the field is now set.
    """
    if getattr(belief, field, None) is not None:
        return True
    low = (message or "").lower()
    if field == "bedrooms_min":
        m = re.search(r"\b(\d{1,2})\b", low)
        if m:
            belief.bedrooms_min = int(m.group(1))
    elif field == "budget_max":
        from app.core.state_transitioner import _parse_budget
        amt = _parse_budget(low)
        if amt:
            belief.budget_max = amt
    elif field == "operation":
        if re.search(r"alquil", low):
            belief.operation = "alquiler"
        elif re.search(r"compr|venta|vender|comprar", low):
            belief.operation = "venta"
    # property_type / zone rely on update_belief's extractors (already ran this turn).
    return getattr(belief, field, None) is not None


async def _run_belief_search(belief):
    """Run search_properties DETERMINISTICALLY from the belief's accumulated criteria.

    The LLM does NOT choose the args, so it can't mix property types or silently drop
    filters (zone/bedrooms/budget). Returns a synthetic agent result compatible with
    _update_belief_from_result and the narrowing check.
    """
    from app.tools.v2.search_properties import search_properties
    args = {
        "operation": belief.operation or "",
        "tipo": belief.property_type or "",
        "zona": belief.zone or "",
        "presupuesto_max": float(belief.budget_max) if belief.budget_max else 0,
        "dormitorios": int(belief.bedrooms_min) if belief.bedrooms_min else 0,
        "bedrooms_match": "exact",
    }
    text = await search_properties(**args)
    return AgentResponse(
        response=text,
        tools_called=["search_properties"],
        raw_tool_results=[{"name": "search_properties", "result": text, "arguments": args}],
        confidence=0.95,
    )


# ── Viewed-property reference resolution ("me interesa más la casa") ───────────

def _extract_detail_title(detail_text: str) -> str:
    """Pull the property title (first non-decorative line) out of a get_property_details blob."""
    for line in (detail_text or "").splitlines():
        s = line.strip().lstrip("🏠").strip()
        if s and "━" not in s and not s[:1] in ("📋", "📍", "💰", "🛏", "🚿", "📐", "✨", "📝"):
            return s
    return ""


def _classify_title_type(title: str) -> "str | None":
    """Map a property title to a canonical type."""
    t = (title or "").lower()
    if "casa" in t:
        return "casa"
    if "departamento" in t or "depto" in t or "monoambiente" in t or " amb" in t:
        return "departamento"
    if "ph" in t:
        return "ph"
    if "terreno" in t or "lote" in t:
        return "terreno"
    return None


def _has_non_type_criteria(message: str) -> bool:
    """True if the message carries a search criterion OTHER than a property type
    (budget, bedrooms, zone, operation) — used to tell a SELECTION ("me interesa la
    casa") apart from a REFINEMENT ("una casa de 1 dormitorio en centro")."""
    from app.core.state_transitioner import (
        BUDGET_PATTERN, BEDROOMS_PATTERN, ZONE_PATTERNS, OPERATION_PATTERNS,
    )
    low = (message or "").lower()
    if BUDGET_PATTERN.search(low) or BEDROOMS_PATTERN.search(low) or _BARE_AMOUNT.search(low):
        return True
    for pattern, _ in (ZONE_PATTERNS + OPERATION_PATTERNS):
        if re.search(pattern, low):
            return True
    return False


def _resolve_viewed_reference(belief, ref_word: str) -> "tuple[str, list[dict]]":
    """Resolve 'la casa'/'el depto' against properties the user VIEWED IN DETAIL.

    Returns (status, matches): status is 'one' | 'many' | 'none'.
    """
    from app.core.state_transitioner import _REF_TYPE_SYNONYMS
    target = _REF_TYPE_SYNONYMS.get((ref_word or "").lower())  # casa/departamento/ph/terreno, or None for "propiedad"
    viewed = belief.viewed_properties or []
    if target:
        matches = [v for v in viewed if v.get("tipo") == target]
    else:
        matches = list(viewed)
    if len(matches) == 1:
        return "one", matches
    if len(matches) >= 2:
        return "many", matches
    return "none", matches


def _parse_search_context(context: str) -> list[dict]:
    """Parse last_search_context into a list of {id, label} dicts.

    Context entries look like:
      "[4] Departamento en Barrio Schuster (Alquiler $46,149/mes)"
    Handles both '|'-separated summaries and raw result text.
    Returns a flat list sorted by id.
    """
    entries = []
    for chunk in re.split(r"\s*\|\s*", context or ""):
        m = re.match(r"\[(\d+)\]\s+(.+?)(?:\s*$|\s*\(.*?\))", chunk.strip())
        if m:
            pid = int(m.group(1))
            label = m.group(2).strip()
            entries.append({"id": pid, "label": label})
    if not entries:
        # Fallback: scan raw text for "[ID] SomeName" patterns
        for m in re.finditer(r"\[(\d+)\]\s+([A-Za-záéíóúüñÁÉÍÓÚÜÑ][^\n\[\]]{3,60})", context or ""):
            entries.append({"id": int(m.group(1)), "label": m.group(2).strip()})
    return entries


def _resolve_description_from_search(
    belief, message: str
) -> "tuple[str, list[dict]]":
    """Resolve a property reference by description (zone/price/type) against the
    current search list.

    Handles the generic case: user says "el de barrio schuster" / "el más barato" /
    "el de la ruta" when there are MULTIPLE matching properties in the last search.
    Checks every IDs entry in last_search_ids against last_search_context.

    Returns (status, matches):
      'one'  – exactly one match → {id, label}
      'many' – 2+ matches → [{id, label}, ...]
      'none' – no useful match
    """
    ids = getattr(belief, "last_search_ids", None) or []
    ctx = getattr(belief, "last_search_context", "") or ""
    if not ids or not ctx:
        return "none", []

    # Index context by id for fast lookup.
    parsed = {e["id"]: e["label"] for e in _parse_search_context(ctx)}
    if not parsed:
        return "none", []

    low = (message or "").lower()

    # ── Step 1: canonical zone detection from the user's message ─────────────────
    # Use the same ZONE_PATTERNS as update_belief so zone typos ("shuster"→"Barrio
    # Schuster") are resolved the same way everywhere.
    from app.core.state_transitioner import ZONE_PATTERNS as _ZPATS
    canonical_zones: set[str] = set()
    for _zpat, _zname in _ZPATS:
        if re.search(_zpat, low, re.IGNORECASE):
            canonical_zones.add(_zname.lower())

    # ── Step 2: fuzzy fallback — if no canonical zone found, compare user tokens to
    # all known zone names using difflib so "shuster" finds "schuster" etc.
    # IMPORTANT: skip generic tokens that appear in many zone names ("barrio", "villa",
    # "hospital") — they would add ALL "barrio X" zones, causing false multi-matches.
    _FUZZY_STOP = {
        "barrio", "villa", "hospital", "zona", "bario", "ruta",
    }
    if not canonical_zones:
        import difflib
        _all_zone_names = [zn.lower() for _, zn in _ZPATS]
        for _tok in re.findall(r"[a-záéíóúñ]{4,}", low):
            if _tok in _FUZZY_STOP:
                continue
            _close = difflib.get_close_matches(_tok, _all_zone_names, n=1, cutoff=0.72)
            if _close:
                canonical_zones.add(_close[0])
            # Also check each word inside zone names (e.g. "schuster" in "barrio schuster")
            for _zn in _all_zone_names:
                for _zword in re.findall(r"[a-záéíóúñ]{4,}", _zn):
                    if _zword in _FUZZY_STOP:
                        continue
                    _cw = difflib.get_close_matches(_tok, [_zword], n=1, cutoff=0.78)
                    if _cw:
                        canonical_zones.add(_zn)

    # ── Step 3: if still nothing, try distinctive raw tokens (exact) ─────────────
    _STOP = {
        "dame", "deme", "pasa", "pase", "info", "mapa",
        "quiero", "quisiera", "podria", "podría", "interesa", "interes",
        "este", "esta", "aquel", "aquella", "cual",
        "departamento", "departamentos", "depto", "deptos", "casa", "casas",
        "propiedad", "propiedades", "inmo", "inmobiliaria",
        "disponible", "disponibles", "alquiler", "venta",
        "favor", "informacion", "detalles", "detalle",
        "barrio", "zona", "calle", "bario", "obera", "misiones",
        "pasas", "podes", "puedes", "podrias", "quiero", "queda",
    }
    raw_tokens = {
        t for t in re.findall(r"[a-záéíóúñ]{4,}", low)
        if t not in _STOP
    }

    # ── Step 4: score each search-list entry ──────────────────────────────────────
    matches = []
    for pid in ids:
        label = parsed.get(pid, "")
        label_low = label.lower()

        # Zone-based match (most reliable)
        if canonical_zones and any(z in label_low for z in canonical_zones):
            matches.append({"id": pid, "label": label})
            continue

        # Raw-token fallback: distinctive overlap between user tokens and label
        if raw_tokens:
            label_tokens = {
                t for t in re.findall(r"[a-záéíóúñ]{4,}", label_low)
                if t not in _STOP
            }
            if raw_tokens & label_tokens:
                matches.append({"id": pid, "label": label})

    if len(matches) == 1:
        return "one", matches
    if len(matches) >= 2:
        return "many", matches
    return "none", []


def _match_disambiguation(message: str, candidates: list) -> "dict | None":
    """Pick a candidate from the user's reply by a distinctive title word or ordinal."""
    low = (message or "").lower()
    _generic = {"casa", "casas", "departamento", "depto", "dormitorios", "dormitorio", "amb", "obera", "misiones"}
    for v in candidates:
        for word in re.findall(r"[a-záéíóúñ]{4,}", (v.get("titulo") or "").lower()):
            if word not in _generic and word in low:
                return v
    if re.search(r"\b(primera|primero|primer|1|una)\b", low) and candidates:
        return candidates[0]
    if re.search(r"\b(segunda|segundo|2|dos)\b", low) and len(candidates) > 1:
        return candidates[1]
    return None


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
    # Photo offer ("te paso las fotos de la propiedad…") — may not be phrased as a question.
    if "fotos" in low and ("propiedad" in low or "te paso" in low or "te mando" in low or "querés" in low or "queres" in low):
        if getattr(belief, "selected_property_id", None):
            return "show_photos"
    is_question = "?" in response or "¿" in response
    if not is_question:
        return None
    # Guard against spurious scheduling entry: only infer a scheduling_* slot when
    # scheduling is actually plausible — i.e. a property is selected, scheduling is
    # already in progress, or the scheduling intent is active. Otherwise a generic
    # "¿cuándo...?" or "...nombre..." in a non-scheduling reply must NOT trap the
    # user in the booking flow.
    _sched_active = (
        getattr(belief, "selected_property_id", None) is not None
        or "scheduling" in (getattr(belief, "active_intents", None) or set())
        or str(getattr(belief, "awaiting", "") or "").startswith("scheduling")
        or bool(getattr(belief, "scheduling_name", ""))
        or bool(getattr(belief, "scheduling_day", ""))
        or bool(getattr(belief, "scheduling_time", ""))
    )
    if not _sched_active:
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


def _next_scheduling_slot(belief) -> "str | None":
    """Return the next scheduling slot that needs collecting, or None if all present.

    Authoritative, belief-state-driven slot advancement for the awaiting fast-path.
    """
    if not getattr(belief, "selected_property_id", None):
        return "scheduling_property"
    # Collect day + time BEFORE the name: the name is the last slot, asked only once
    # the concrete slot is settled (so an ambiguous "sí" can never land as the name,
    # and we never confirm a booking with an empty time).
    if not getattr(belief, "scheduling_day", None):
        return "scheduling_day"
    if not getattr(belief, "scheduling_time", None):
        return "scheduling_time"
    if not getattr(belief, "scheduling_name", None):
        return "scheduling_name"
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


# LLM "the visit is booked" claims emitted WITHOUT actually calling schedule_visit.
# These must never reach the user as-is — they are fake confirmations.
_FAKE_BOOKING = re.compile(
    r"(dejo\s+(?:la\s+)?(?:visita\s+)?solicitad"
    r"|qued[ao]\s+(?:agendad|coordinad|reservad|confirmad|registrad)"
    r"|visita\s+(?:agendad|confirmad|coordinad|reservad|registrad|anotad)"
    r"|(?:te\s+)?(?:la\s+)?anot[oé]\s+(?:la\s+)?visita|te\s+anoto\s+(?:la\s+)?visita"
    r"|ya\s+(?:te\s+la\s+|la\s+)?agend|agend[ée]\s+(?:la\s+)?visita"
    r"|reserv[ée]\s+(?:la\s+)?visita|coordin[ée]\s+(?:la\s+)?visita"
    r"|visita\s+(?:para\s+el|para\s+ma[nñ]ana).{0,40}\b(?:hs|horas?|:\d{2})"
    r"|lista\s+(?:la\s+)?visita|ya\s+est[áa]\s+(?:la\s+)?visita)",
    re.IGNORECASE,
)
# Markers that mean schedule_visit was called but did NOT succeed.
_SCHED_FAILED_MARKERS = (
    "⚠️", "no pude", "faltan datos", "me falta", "los domingos",
    "el horario de las", "tuve un problema", "fuera de", "está ocupado",
)


async def _resolve_scheduling_datetime(belief) -> "datetime | None":
    """Resolve belief.scheduling_day + scheduling_time into a concrete datetime,
    using the SAME parser schedule_visit uses (so the availability check matches the
    eventual booking). Returns None if it can't be resolved."""
    try:
        from app.core.hybrid.date import date_parser as _hybrid_date_parser
        from app.utils.date_parser import get_argentina_now as _ar_now
        from datetime import timedelta as _td
        now = _ar_now()
        day = getattr(belief, "scheduling_day", "") or ""
        tm = getattr(belief, "scheduling_time", "") or ""
        combined = f"{day} {tm}".strip()
        if not combined:
            return None
        res = await _hybrid_date_parser.parse(
            combined, {"date_str": day, "time_str": tm, "reference_dt": now},
        )
        dt = getattr(res, "value", None)
        if dt is None:
            return None
        # Roll forward past times (mirror schedule_visit) so a same-day past slot
        # checks the next week, not a stale moment.
        try:
            if dt <= now:
                dt = dt + _td(days=7)
        except TypeError:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=now.tzinfo)
            if dt <= now:
                dt = dt + _td(days=7)
        return dt
    except Exception as e:
        logger.warning(f"[Scheduling] datetime resolve failed (fail-open): {e}")
        return None


async def _check_slot_or_suggest(belief) -> "str | None":
    """Check if the proposed day/time is FREE before confirming. Returns None when the
    slot is available (or can't be checked → fail-open), or a user-facing message
    offering nearby available slots when it is taken."""
    try:
        pid = getattr(belief, "selected_property_id", None)
        if not pid:
            return None
        dt = await _resolve_scheduling_datetime(belief)
        if dt is None:
            return None
        from app.services.appointment_service import appointment_service
        avail = await appointment_service.check_slot_availability(pid, dt)
        if avail.get("available", True):
            return None
        sugg = avail.get("suggested_times", []) or []
        if sugg:
            lines = "\n".join(f"• {s.get('formatted', '')}" for s in sugg[:3] if s.get("formatted"))
            return (
                f"Uy, el {belief.scheduling_day} a las {belief.scheduling_time} ya está "
                f"ocupado 😕\n\nTengo estos horarios disponibles:\n{lines}\n\n¿Alguno te sirve?"
            )
        return (
            f"Uy, el {belief.scheduling_day} a las {belief.scheduling_time} ya está "
            "ocupado 😕. ¿Qué otro día u horario te viene bien?"
        )
    except Exception as e:
        logger.warning(f"[Scheduling] availability check failed (fail-open): {e}")
        return None


async def _maybe_confirm_or_pass(belief, result, session_id: str) -> "tuple[str, str]":
    """If all scheduling fields present and not yet confirming, inject confirm step.

    Hardened against scheduling bugs:
      • P10 — schedule_visit called but FAILED → never surface as success.
      • P1  — LLM fakes "dejo la visita solicitada" → never reaches the user.
      • Name slot — once day+time+property are known, ask the NAME explicitly (not a
        redundant day/time re-confirmation), so an ambiguous "sí" is never captured as
        the visitor's name.
      • Availability — verify the slot is FREE (DB + calendar) BEFORE asking the name
        or confirming; if taken, offer nearby available slots instead.
    """
    _resp = result.response or ""
    _booked = bool(result.tools_called and "schedule_visit" in result.tools_called)
    _failed = any(m in _resp.lower() for m in _SCHED_FAILED_MARKERS)
    # Genuine success: tool called AND no failure markers.
    if _booked and not _failed:
        return _resp, "scheduling::booked"

    # Persist any concrete slot the specialist just PROPOSED in its reply
    # ("¿Te quedaría bien el martes 09/06 a las 15:00?") so the visible suggestion
    # becomes authoritative state — otherwise the booking can never assemble a
    # complete day+time and the flow stalls or silently drops the booking.
    _capture_proposed_slot(belief, _resp)

    _name = getattr(belief, "scheduling_name", None)
    _day = getattr(belief, "scheduling_day", None)
    _time = getattr(belief, "scheduling_time", None)
    _pid = getattr(belief, "selected_property_id", None)
    have_slot = bool(_day and _time and _pid)
    have_all = bool(have_slot and _name)
    _awaiting = getattr(belief, "awaiting", None)

    # Day+time known but NO name yet → verify the slot, then ask the name explicitly.
    if have_slot and not _name and _awaiting != "scheduling_confirm":
        _taken = await _check_slot_or_suggest(belief)
        if _taken is not None:
            belief.scheduling_time = ""        # drop the occupied time
            belief.awaiting = "scheduling_time"
            belief.last_bot_message = _taken
            return _taken, "scheduling::slot-taken"
        belief.awaiting = "scheduling_name"
        ask = (
            f"Genial, el {belief.scheduling_day} a las {belief.scheduling_time} 👍. "
            "¿A nombre de quién registro la visita?"
        )
        belief.last_bot_message = ask
        return ask, "scheduling::ask-name"

    if have_all and _awaiting != "scheduling_confirm":
        _taken = await _check_slot_or_suggest(belief)
        if _taken is not None:
            belief.scheduling_time = ""
            belief.awaiting = "scheduling_time"
            belief.last_bot_message = _taken
            return _taken, "scheduling::slot-taken"
        belief.awaiting = "scheduling_confirm"
        confirm = (
            f"¿Confirmo la visita para el {belief.scheduling_day} a las "
            f"{belief.scheduling_time} a nombre de {belief.scheduling_name}? "
            "Respondé Sí para confirmar."
        )
        belief.last_bot_message = confirm
        return confirm, "scheduling::confirm-request"
    # Fake confirmation (P1) or a failed schedule_visit (P10) with slots still missing:
    # never surface it — ask for the next missing slot deterministically.
    if (not _booked and _FAKE_BOOKING.search(_resp)) or (_booked and _failed):
        _slot = _next_scheduling_slot(belief) or "scheduling_day"
        belief.awaiting = _slot
        _q = {
            "scheduling_property": "¿Sobre cuál de las propiedades querés coordinar la visita?",
            "scheduling_name": "Genial 👍 ¿A nombre de quién registro la visita?",
            "scheduling_day": "¿Qué día te quedaría bien para la visita?",
            "scheduling_time": "¿En qué horario te viene mejor?",
        }.get(_slot, "¿Qué día y horario te quedan bien para la visita?")
        belief.last_bot_message = _q
        return _q, "scheduling::missing-slot-reask"
    return _resp, "scheduling::collecting"


_SCHED_NAME_CUE = re.compile(
    r"\b(?:soy|me\s+llamo|mi\s+nombre\s+es|a\s+nombre\s+de)\s+"
    r"([a-záéíóúñ]+(?:\s+[a-záéíóúñ]+){0,2})\b",
    re.IGNORECASE,
)
_NAME_STOPWORDS = {
    "el", "la", "yo", "un", "una", "de", "para", "mañana", "manana", "tarde",
    "noche", "hoy", "lunes", "martes", "miercoles", "miércoles", "jueves",
    "viernes", "sabado", "sábado", "domingo", "que", "y", "las", "los",
}


def _capture_name(belief, message: str) -> None:
    """Capture the visitor's name from an explicit cue ("soy X", "me llamo X",
    "a nombre de X") into belief.scheduling_name, when not already set.

    Deterministic complement to the LLM name extractor (B4): lets a name bundled in
    a dense scheduling message ("agendá para mañana 10, soy carla gomez") populate
    the slot so the booking doesn't re-ask for it.
    """
    if getattr(belief, "scheduling_name", None):
        return
    m = _SCHED_NAME_CUE.search(message or "")
    if not m:
        return
    cand = m.group(1).strip()
    if not cand or cand.split()[0].lower() in _NAME_STOPWORDS:
        return
    belief.scheduling_name = cand.title()


def _capture_day_time(belief, message: str) -> None:
    """Persist scheduling day/time from the user's message into belief state.

    Only writes a field if the extractor finds something AND the field is not
    already set. Safe to call on any turn; extractors return None when no
    concrete value is present.
    """
    try:
        if not getattr(belief, "scheduling_day", ""):
            day = extract_scheduling_day(message)
            if day:
                belief.scheduling_day = day
        if not getattr(belief, "scheduling_time", ""):
            t = extract_scheduling_time(message)
            if t:
                belief.scheduling_time = t
    except Exception as e:
        logger.debug(f"[Scheduling] day/time capture skipped: {e}")


def _capture_proposed_slot(belief, bot_text: str) -> None:
    """Persist a concrete day/time the BOT itself proposed in its message
    ("¿Te quedaría bien el martes 09/06 a las 15:00 hs?") into the belief, so the
    suggestion the user actually sees becomes authoritative state.

    Without this, a slot the specialist proposes lives only in the reply text: the
    booking can never assemble a complete date (time stays empty), the slot order
    skips ahead to the name, and a later "sí" + name produces no booking. Only fills
    EMPTY fields; the extractors return None when no concrete value is present, so a
    plain "¿qué día te viene bien?" writes nothing.
    """
    if not bot_text:
        return
    try:
        if not getattr(belief, "scheduling_day", ""):
            day = extract_scheduling_day(bot_text)
            if day:
                belief.scheduling_day = day
        if not getattr(belief, "scheduling_time", ""):
            t = extract_scheduling_time(bot_text)
            if t:
                belief.scheduling_time = t
    except Exception:
        pass


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
        ids_match = re.findall(r"(?:ID:|\[)(\d+)", result)
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
    
    # Case 1c: Pure selection of a LISTED property by ID/ordinal → show details now.
    # After a search list, "me interesa el 8" / "el segundo" / "quiero el 4" picks one
    # option — show its full details automatically instead of a generic teaser. Gated
    # on (a) the selection happening THIS turn (selection phrasing present) and (b) the
    # chosen ID belonging to the last search list, so it never fires on a stale id or a
    # bundled scheduling/photo/compare request.
    if (belief.selected_property_id
            and belief.selected_property_id in (getattr(belief, "last_search_ids", None) or [])
            and _is_pure_selection(message)):
        pid = belief.selected_property_id
        result_text = await get_property_details(property_id=pid)
        belief.last_tool_called = "get_property_details"
        _extract_property_data(belief, result_text)
        cta = "\n\n¿Querés ver las fotos o coordinar una visita para conocerla en persona?"

        # Bundled question ("me interesa el 2, ¿el precio incluye los servicios?") →
        # show the details AND answer the question, as two sequential messages. The
        # knowledge specialist answers using the property's own data (or the FAQ),
        # scoped to this property so it doesn't repeat the card or the list.
        _has_q = ("?" in message or "¿" in message) and len(message.split()) >= 5
        if _has_q:
            try:
                from app.agents.s2_agent import process_message_with_specialist
                from app.agents.coordinator import SPECIALISTS
                _hint = (
                    f"[CONTEXTO] El usuario ya eligió la propiedad #{pid} y sus detalles se "
                    f"le están mostrando en este mismo turno. Respondé SOLO la consulta "
                    f"puntual que hace sobre esa propiedad, sin repetir la ficha ni la lista. "
                    f"Si la info no figura en la propiedad, usá get_faq_answer (política "
                    f"general) y aclaralo.\n"
                )
                _ans = await process_message_with_specialist(
                    message=message,
                    session_id=session_id,
                    context_prompt=_hint,
                    specialist=SPECIALISTS["knowledge"],
                )
                _ans_text = (_ans.response or "").strip()
                if _ans_text:
                    _chunks = [
                        MessageChunk(text=result_text, tool_used="get_property_details", chunk_type="faq"),
                        MessageChunk(text=_ans_text + cta, chunk_type="faq"),
                    ]
                    _tools = ["get_property_details"] + list(getattr(_ans, "tools_called", []) or [])
                    return (
                        ChatResponse(
                            response=result_text,
                            tools_called=_tools,
                            confidence=0.97,
                            messages=_chunks,
                        ),
                        _tools, 0.97, "pre-llm::selection+faq",
                    )
            except Exception as _e:
                logger.warning(f"[Router] selection+faq bundled answer failed (fallback to details): {_e}")

        return (
            ChatResponse(
                response=result_text + cta,
                tools_called=["get_property_details"],
                confidence=0.99,
            ),
            ["get_property_details"],
            0.99,
            "pre-llm::list-selection",
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

    # Case 4: Detail request for a property identified by TYPE + ZONE from search history.
    # "me pasas también los detalles de la casa en el centro?" — the user is pointing to a
    # property they saw in a previous search list (not the last one, not a viewed one).
    # update_belief() already ran: belief.zone = extracted zone, belief.property_type = type.
    # We look for a matching ID in belief.search_history and call get_property_details directly,
    # avoiding the LLM coordinator which gets confused by contradictory context (selected=UNAM
    # casa but zone now=Centro).
    # Broad "detail keyword" match — specificity comes from zone-in-message + search_history guards.
    # Handles both "pasame los detalles" and "me pasas los detalles" (Spanish clitic variations).
    _DETAIL_HIST_PAT = re.compile(
        r"\b(?:detall(?:es?)|informaci[oó]n|info|datos|caracter[ií]sticas)\b",
        re.IGNORECASE,
    )
    if (
        _DETAIL_HIST_PAT.search(msg_lower)
        and getattr(belief, "search_history", None)
        and getattr(belief, "zone", None)
        and getattr(belief, "property_type", None)
    ):
        # Guard: the zone must be explicitly in THIS message (not stale from a prior turn).
        # Use the same zone-extraction patterns as update_belief.
        from app.core.state_transitioner import ZONE_PATTERNS as _ZPATS
        _zone_in_this_msg = any(re.search(p, message.lower()) for p, _ in _ZPATS)
        if _zone_in_this_msg:
            _tgt_tipo = belief.property_type.lower()
            _tgt_zona = belief.zone.lower()
            for _hist in reversed(belief.search_history):
                _hist_zona = (_hist.get("criteria", {}).get("zona") or "").lower()
                if not _hist_zona:
                    continue
                # Zone match (substring check covers "centro" ↔ "Centro" etc.)
                if _hist_zona in _tgt_zona or _tgt_zona in _hist_zona:
                    _hist_ctx = _hist.get("context", "")
                    for _hid in _hist.get("ids", []):
                        # Skip if we already showed this property's details this session
                        if _hid == getattr(belief, "last_shown_detail_id", None):
                            continue
                        # Match tipo in context string: "[22] Casa en Centro"
                        if re.search(rf"\[{_hid}\]\s*{_tgt_tipo}", _hist_ctx, re.IGNORECASE):
                            logger.info(
                                f"[Router] 🔍 History-detail resolver: "
                                f"prop #{_hid} ({_tgt_tipo} en {_tgt_zona}) for {session_id}"
                            )
                            belief.selected_property_id = _hid
                            det_text = await get_property_details(property_id=_hid)
                            belief.last_tool_called = "get_property_details"
                            belief.last_shown_detail_id = _hid
                            _extract_property_data(belief, det_text)
                            # Track in viewed_properties
                            _vt = _extract_detail_title(det_text) or f"propiedad #{_hid}"
                            _vt_tipo = _classify_title_type(_vt) or _tgt_tipo
                            belief.viewed_properties = [
                                v for v in belief.viewed_properties if v.get("id") != _hid
                            ]
                            belief.viewed_properties.append(
                                {"id": _hid, "tipo": _vt_tipo, "titulo": _vt}
                            )
                            belief.viewed_properties = belief.viewed_properties[-10:]
                            return (
                                ChatResponse(
                                    response=det_text,
                                    tools_called=["get_property_details"],
                                    confidence=0.95,
                                ),
                                ["get_property_details"],
                                0.95,
                                "pre-llm::detail-from-history",
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

    # ── Explicit human-handoff request (schema v4) ────────────
    # Top priority: if the user asks for a real person, escalate immediately —
    # even mid-scheduling or alongside complaints ("todo caro, quiero una persona").
    # This must run BEFORE specialist routing so keyword-based routing (e.g.
    # "caro" → negotiator) can't swallow the escalation.
    if _is_human_request(message):
        logger.info(f"[Router] Human handoff requested for {session_id}: {message[:80]}")
        try:
            from app.tools.v2.request_human_assistance import request_human_assistance as _rha
            handoff = await _rha(reason="user_requested", message=message)
        except Exception:
            handoff = "Te comunico con un asesor para que te atienda personalmente."
        belief.consecutive_failures = 0
        belief.awaiting = None
        belief.last_bot_message = handoff
        await clear_saved_state(session_id)
        await save_working_memory(belief)
        return (
            ChatResponse(response=handoff, tools_called=["request_human_assistance"], confidence=1.0),
            belief, "human-handoff", 0,
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

    # ── AWAITING: photo offer ──────────────────────────────────
    if getattr(belief, "awaiting", None) == "show_photos":
        if _is_hard_topic_switch(message):
            belief.awaiting = None
            # Fall through to normal routing below.
        elif _is_negative(message):
            belief.awaiting = None
            resp = "Entendido, ¿hay algo más en lo que te pueda ayudar?"
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.95),
                belief, "awaiting::photos-decline", 0,
            )
        elif _is_confirmation(message) and getattr(belief, "selected_property_id", None):
            from app.tools.v2.get_property_images import get_property_images
            import json as _json
            result_text = await get_property_images(property_id=belief.selected_property_id)
            try:
                display_text = _json.loads(result_text).get("display_text", result_text)
            except Exception:
                display_text = result_text
            belief.last_tool_called = "get_property_images"
            belief.awaiting = None
            belief.last_bot_message = display_text
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=display_text, tools_called=["get_property_images"], confidence=0.99),
                belief, "awaiting::photos", 0,
            )
        else:
            # Neither confirm nor negative nor topic switch → clear and route normally.
            belief.awaiting = None

    # ── AWAITING FAST-PATH (schema v4) ────────────────────────
    if getattr(belief, "awaiting", None) and belief.awaiting.startswith("scheduling_"):

        # B1. Hard topic switch → exit scheduling flow, fall through.
        if _is_hard_topic_switch(message):
            belief.awaiting = None
            _clear_scheduling_state(belief)
            await clear_saved_state(session_id)
            # Do NOT return — fall through to normal routing.

        # B1.5 Slot rejection / change: "ese día no puedo, otro día?", "otra hora".
        # Fires for ANY scheduling_* slot (incl. confirm). Clears the rejected slot(s),
        # captures any new day/time bundled in the same message, and asks for what's
        # missing — no "¿Seguimos…?" spam, no full cancel.
        elif _is_slot_change_request(message) and not _is_confirmation(message):
            _rej_day = bool(_REJECT_DAY.search(message))
            # A day change invalidates the previously proposed time too.
            if _rej_day:
                belief.scheduling_day = ""
                belief.scheduling_time = ""
            else:
                belief.scheduling_time = ""
            # The user may have supplied a NEW slot in the same breath
            # ("el viernes no, mejor el martes a las 10").
            _capture_day_time(belief, message)
            if not belief.scheduling_day:
                belief.awaiting = "scheduling_day"
                resp = "Sin problema 👍 ¿Qué otro día te queda bien para la visita?"
                _label = "awaiting::slot-change-day"
            elif not belief.scheduling_time:
                belief.awaiting = "scheduling_time"
                resp = (
                    f"Perfecto, el {belief.scheduling_day} 👍 "
                    "¿En qué horario te viene mejor?"
                )
                _label = "awaiting::slot-change-time"
            else:
                _taken = await _check_slot_or_suggest(belief)
                if _taken is not None:
                    belief.scheduling_time = ""
                    belief.awaiting = "scheduling_time"
                    resp = _taken
                    _label = "awaiting::slot-change-taken"
                elif belief.scheduling_name:
                    belief.awaiting = "scheduling_confirm"
                    resp = (
                        f"¿Confirmo la visita para el {belief.scheduling_day} a las "
                        f"{belief.scheduling_time} a nombre de {belief.scheduling_name}? "
                        "Respondé Sí para confirmar."
                    )
                    _label = "awaiting::slot-change-confirm"
                else:
                    belief.awaiting = "scheduling_name"
                    resp = (
                        f"Genial, el {belief.scheduling_day} a las {belief.scheduling_time} 👍. "
                        "¿A nombre de quién registro la visita?"
                    )
                    _label = "awaiting::slot-change-name"
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.92),
                belief, _label, 0,
            )

        # B2. Confirmation step.
        elif belief.awaiting == "scheduling_confirm":
            # Wrong-name correction → re-ask the name (keep day/time/property); do NOT
            # cancel. "ese no es mi nombre", "está mal el nombre", "no me llamo así",
            # or a correction that supplies the right name ("no, soy Juan Pérez").
            _low_c = message.lower()
            _mentions_name = bool(re.search(r"\bnombre\b|\bme llamo\b|\bme dicen\b", _low_c))
            _name_wrong = bool(
                re.search(r"\b(no|mal|equivoc|otro|cambi|corre|corregi|distinto)\b", _low_c)
                or _SCHED_NAME_CUE.search(message)
            )
            if (not _is_confirmation(message)) and _mentions_name and _name_wrong:
                belief.scheduling_name = ""
                _capture_name(belief, message)  # maybe they gave the correct one
                if belief.scheduling_name:
                    # Got the corrected name → re-confirm with it.
                    belief.awaiting = "scheduling_confirm"
                    resp = (
                        f"¡Perfecto! ¿Confirmo la visita para el {belief.scheduling_day} a las "
                        f"{belief.scheduling_time} a nombre de {belief.scheduling_name}? "
                        "Respondé Sí para confirmar."
                    )
                else:
                    belief.awaiting = "scheduling_name"
                    resp = "Perdón 🙏 ¿A nombre de quién registro la visita?"
                belief.last_bot_message = resp
                belief.consecutive_failures = 0
                await save_working_memory(belief)
                return (
                    ChatResponse(response=resp, tools_called=[], confidence=0.95),
                    belief, "awaiting::name-correction", 0,
                )
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

        # B3. Mid-flow interruption: user asks something else (not a topic switch).
        # "Atender y mantener pendiente" — answer the new ask with the RIGHT
        # specialist/tool, keep the scheduling flow pending, and offer to resume.
        # GUARD: a slot answer phrased as a question ("a las 5 podría ser?",
        # "el martes que viene?") is NOT an interruption — let it fall through to the
        # slot-capture path (B5) so the day/time persists and we don't spam "¿Seguimos…?".
        elif ("?" in message or "¿" in message) and not _looks_like_scheduling_answer(message):
            _low = message.lower()
            _pid = getattr(belief, "selected_property_id", None)
            _tools: list = []
            _answer_text = ""

            # (a) Photo request on the active property → answer directly.
            if _pid and re.search(r"\b(fotos?|im[aá]gen(?:es)?)\b", _low):
                from app.tools.v2.get_property_images import get_property_images
                import json as _json
                _raw = await get_property_images(property_id=_pid)
                try:
                    _answer_text = _json.loads(_raw).get("display_text", _raw)
                except Exception:
                    _answer_text = _raw
                belief.last_tool_called = "get_property_images"
                _tools = ["get_property_images"]

            # (b) Detail / feature question on the active property → answer directly.
            elif _pid and re.search(
                r"\b(detalles?|caracter[ií]sticas|garaje|cochera|patio|quincho|"
                r"metros|m2|m²|superficie|ambientes?|dormitorios?|ba[ñn]os?|"
                r"tiene|cu[aá]ntos?)\b", _low,
            ):
                from app.tools.v2.get_property_details import get_property_details
                _answer_text = await get_property_details(property_id=_pid)
                belief.last_tool_called = "get_property_details"
                _tools = ["get_property_details"]

            # (c) New search vs FAQ → delegate to the matching specialist.
            else:
                from app.agents.s2_agent import process_message_with_specialist
                from app.agents.coordinator import SPECIALISTS
                _is_new_search = _message_has_search_criteria(message) or re.search(
                    r"\b(terrenos?|lotes?|casas?|departamentos?|deptos?|monoambientes?|"
                    r"ph|otra propiedad|otra opci[oó]n|otras opciones)\b", _low,
                )
                _spec = SPECIALISTS["search"] if _is_new_search else SPECIALISTS["knowledge"]
                answer = await process_message_with_specialist(
                    message=message,
                    session_id=session_id,
                    context_prompt=context_prompt,
                    specialist=_spec,
                    recent_messages=recent_messages,
                )
                _answer_text = answer.response
                _tools = getattr(answer, "tools_called", [])

            resp = _answer_text + "\n\n¿Seguimos con el agendamiento de la visita?"
            # Keep belief.awaiting unchanged — scheduling stays pending.
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=_tools, confidence=0.9),
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
            # Also capture day/time if the user bundled them with their name.
            _capture_day_time(belief, message)
            # Fall through to scheduling specialist for next slot.
            sched_context = _build_scheduling_context(belief) + "\n" + (context_prompt or "")
            result, _ = await coordinate(message, session_id, sched_context, recent_messages=recent_messages)
            await save_specialist_state(session_id, "scheduling")
            _update_belief_from_result(belief, result)
            await _finalize_turn(belief, session_id, result.response)
            resp_text, label = await _maybe_confirm_or_pass(belief, result, session_id)
            # Authoritative slot advancement — don't rely on text detection.
            if belief.awaiting != "scheduling_confirm":
                belief.awaiting = _next_scheduling_slot(belief)
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp_text, tools_called=getattr(result, "tools_called", []),
                             confidence=getattr(result, "confidence", 0.9)),
                belief, label, 0,
            )

        # B5. Any other scheduling_* slot (day / time / property).
        else:
            # PRIMARY FIX: persist day/time from user's message BEFORE building context
            _capture_day_time(belief, message)
            sched_context = _build_scheduling_context(belief) + "\n" + (context_prompt or "")
            result, _ = await coordinate(message, session_id, sched_context, recent_messages=recent_messages)
            await save_specialist_state(session_id, "scheduling")
            _update_belief_from_result(belief, result)
            await _finalize_turn(belief, session_id, result.response)
            resp_text, label = await _maybe_confirm_or_pass(belief, result, session_id)
            # Authoritative slot advancement — don't rely on text detection.
            if belief.awaiting != "scheduling_confirm":
                belief.awaiting = _next_scheduling_slot(belief)
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp_text, tools_called=getattr(result, "tools_called", []),
                             confidence=getattr(result, "confidence", 0.9)),
                belief, label, 0,
            )

    # ── AWAITING: narrowing-criterion answer ─────────────────────────
    # The bot asked for one or two missing criteria because the last search was too
    # broad. `_nfields` may be a comma-separated list (e.g. "zone,bedrooms_min") when
    # two criteria were requested at once — capture whichever the user provided.
    _in_narrow = str(getattr(belief, "awaiting", "") or "").startswith("search_narrow:")
    if _in_narrow and _NARROW_ESCAPE.search(message):
        # Not a narrowing answer — user references a property / asks details|photos /
        # wants to schedule / asks for cheaper. Clear awaiting and fall through to the
        # normal routing below instead of re-running the same broad search.
        logger.info(
            f"[Router] 🚪 narrowing escape (non-answer intent) for {session_id}: {message[:60]}"
        )
        belief.awaiting = None
        _in_narrow = False
    if _in_narrow:
        _fields_str = belief.awaiting.split(":", 1)[1]
        _nfields = [f.strip() for f in _fields_str.split(",")]
        belief.awaiting = None
        _show_all = bool(_SHOW_ALL_ANYWAY.search(message))
        if not _show_all:
            for _nf in _nfields:
                _capture_narrow_field(belief, _nf, message)
        # Re-run deterministically with the (possibly) added criterion.
        result = await _run_belief_search(belief)
        _update_belief_from_result(belief, result)
        _narrow = None if _show_all else (
            _maybe_narrow_search(belief)
            if "search_properties" in (getattr(result, "tools_called", []) or [])
            else None
        )
        if _narrow:
            _ntext, _nf = _narrow
            belief.awaiting = f"search_narrow:{_nf}"
            belief.last_bot_message = _ntext
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=_ntext, tools_called=getattr(result, "tools_called", []), confidence=0.9),
                belief, "search-narrow", 0,
            )
        await _finalize_turn(belief, session_id, result.response)
        await save_working_memory(belief)
        return (
            ChatResponse(
                response=result.response,
                tools_called=getattr(result, "tools_called", []),
                confidence=getattr(result, "confidence", 0.9),
                messages=getattr(result, "messages", []),
            ),
            belief, "search-narrow-resolved", 0,
        )

    # ── AWAITING: disambiguation between viewed properties ────────────
    # The bot asked "¿Te referís a A o B?" — resolve the user's reply.
    if getattr(belief, "awaiting", None) == "disambiguate_property":
        belief.awaiting = None
        _cands = [v for v in (belief.viewed_properties or [])
                  if v.get("id") in (belief.disambiguation_candidates or [])]
        _pick = _match_disambiguation(message, _cands)
        belief.disambiguation_candidates = []
        if _pick:
            belief.selected_property_id = _pick["id"]
            resp = (
                f"Perfecto 👍 ¿Tenés alguna consulta sobre {_pick['titulo']}, "
                f"o querés que coordinemos una visita para verla en persona?"
            )
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.95),
                belief, "select-disambiguated", 0,
            )
        # Couldn't resolve → fall through to normal routing.

    # ── Selection by reference to a VIEWED property ("me interesa más la casa") ──
    # Resolve against properties the user saw IN DETAIL — not a fresh search.
    _pref = _PREFERENCE_REF.search(message)
    if (_pref and belief.viewed_properties
            and not _has_non_type_criteria(message)
            and not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling_"))):
        _status, _matches = _resolve_viewed_reference(belief, _pref.group(1))
        if _status == "one":
            _m = _matches[0]
            belief.selected_property_id = _m["id"]
            belief.disambiguation_candidates = []
            resp = (
                f"Perfecto 👍 ¿Tenés alguna consulta sobre {_m['titulo']}, "
                f"o querés que coordinemos una visita para verla en persona?"
            )
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.95),
                belief, "select-viewed", 0,
            )
        if _status == "many":
            belief.disambiguation_candidates = [m["id"] for m in _matches]
            belief.awaiting = "disambiguate_property"
            _titles = " o ".join(m["titulo"] for m in _matches[:3])
            resp = f"¿Te referís a {_titles}?"
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.9),
                belief, "select-disambiguate", 0,
            )
        # status == "none" → fall through to normal routing.

    # ── Ambiguous description reference: ask which property ───────────────────────
    # When the user refers to a property by zone/type/description ("el de barrio
    # schuster", "el más barato", "el de la ruta") and there are MULTIPLE candidates
    # in the current search list that match, ask for clarification BEFORE fetching
    # details. Generalises over any description attribute — zone, price tier, type.
    # Gating: only when no property is selected yet, no scheduling is in progress,
    # the message is NOT a pure ID/ordinal selection, and there IS a search list.
    _should_check_desc = (
        not getattr(belief, "selected_property_id", None)
        and getattr(belief, "last_search_ids", None)
        and not (getattr(belief, "awaiting", None) and str(belief.awaiting or "").startswith("scheduling_"))
        and not _is_pure_selection(message)
        and not _is_faq_question(message)
        and not _is_search_refinement(belief, message)
        and not _SCHEDULING_VERB.search(message)
    )
    if _should_check_desc:
        _desc_status, _desc_matches = _resolve_description_from_search(belief, message)
        if _desc_status == "one":
            # Unambiguous description → set id and fall through to the detail shortcut
            belief.selected_property_id = _desc_matches[0]["id"]
            logger.info(f"[Router] 🎯 Desc→ID (unambiguous) {_desc_matches[0]['id']} for {session_id}: {message[:60]}")
        elif _desc_status == "many":
            # Multiple matches → build a contextual disambiguation question.
            belief.disambiguation_candidates = [m["id"] for m in _desc_matches]
            belief.awaiting = "disambiguate_property"
            # Build a short, human-readable list of the candidates for the question.
            _labels = _desc_matches[:4]
            if len(_labels) == 2:
                _opts = " o ".join(
                    f"el [{m['id']}] en {m['label'].replace('Departamento en','').replace('Casa en','').strip()}"
                    for m in _labels
                )
                resp = f"Hay {len(_desc_matches)} opciones en esa zona 😊 ¿A cuál te referís? {_opts}?"
            else:
                _list = "\n".join(
                    f"• [{m['id']}] {m['label']}"
                    for m in _labels
                )
                resp = f"Tengo varias opciones que coinciden:\n{_list}\n\n¿A cuál te referís? Podés decirme el número."
            belief.last_bot_message = resp
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            logger.info(f"[Router] ❓ Ambiguous desc ({len(_desc_matches)} matches) for {session_id}: {message[:60]}")
            return (
                ChatResponse(response=resp, tools_called=[], confidence=0.9),
                belief, "desc-disambiguate", 0,
            )
        # _desc_status == "none" → fall through normally

    # ── Multi-intent: photos + scheduling in one message (FIX 6) ──
    # "quiero ver las fotos y también agendar una visita" → show photos FIRST,
    # then kick off the scheduling flow in the same turn. Without this the bot
    # would pick one intent (scheduling) and silently drop the photo request.
    _mi_pid = getattr(belief, "selected_property_id", None)
    if (_mi_pid
            and not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling_"))
            and re.search(r"\b(fotos?|im[aá]gen(?:es)?)\b", message.lower())
            and re.search(r"\b(agendar|agend[aá]|agendarme|visita|visitar|coordinar|coordin[aá]|turno|cita)\b", message.lower())):
        logger.info(f"[Router] 🎯 Multi-intent photos+scheduling for {session_id}: {message[:80]}")
        from app.tools.v2.get_property_images import get_property_images
        import json as _json
        _raw = await get_property_images(property_id=_mi_pid)
        try:
            _photos_text = _json.loads(_raw).get("display_text", _raw)
        except Exception:
            _photos_text = _raw
        belief.last_tool_called = "get_property_images"
        # Kick off scheduling: capture any day/time bundled in this message.
        _capture_day_time(belief, message)
        belief.active_intents.add("scheduling")
        await save_specialist_state(session_id, "scheduling")
        # Advance to the next scheduling slot we still need.
        belief.awaiting = _next_scheduling_slot(belief) or "scheduling_day"
        if belief.awaiting == "scheduling_day":
            _kick = "Y para la visita, ¿qué día te quedaría bien?"
        elif belief.awaiting == "scheduling_time":
            _kick = "Y para la visita, ¿en qué horario te queda mejor?"
        elif belief.awaiting == "scheduling_name":
            _kick = "Y para coordinar la visita, ¿a nombre de quién la dejo?"
        else:
            _kick = "Y avanzamos con la visita: ¿qué día te quedaría bien?"
        resp = f"{_photos_text}\n\n{_kick}"
        belief.last_bot_message = resp
        belief.consecutive_failures = 0
        await save_working_memory(belief)
        return (
            ChatResponse(response=resp, tools_called=["get_property_images"], confidence=0.95),
            belief, "multi-intent::photos+scheduling", 0,
        )

    # ── Relative budget refinement fast-path ("algo más barato") ──────
    # "más barato / más económico" carries no concrete number, so the generic
    # refinement detector below skips it and the message fell into the narrowing
    # loop ("¿en qué zona?"). Handle it explicitly: if a budget anchor exists,
    # lower it 20% and re-search; otherwise ask for the budget (not the zone).
    _rel_budget = re.search(r"\bm[aá]s\s+(?:barat|econ[oó]mic)", message.lower())
    if (_rel_budget
            and getattr(belief, "last_search_ids", None)
            and not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling_"))
            and not _SCHEDULING_VERB.search(message)):
        if getattr(belief, "budget_max", None):
            belief.budget_max = round(float(belief.budget_max) * 0.8)
            logger.info(f"[Router] 💸 relative-cheaper → budget_max={belief.budget_max} for {session_id}")
            result = await _run_belief_search(belief)
            _update_belief_from_result(belief, result)
            _narrow = (
                _maybe_narrow_search(belief)
                if "search_properties" in (getattr(result, "tools_called", []) or [])
                else None
            )
            if _narrow:
                _ntext, _nfield = _narrow
                belief.awaiting = f"search_narrow:{_nfield}"
                belief.last_bot_message = _ntext
                belief.consecutive_failures = 0
                await save_working_memory(belief)
                return (
                    ChatResponse(response=_ntext, tools_called=getattr(result, "tools_called", []), confidence=0.9),
                    belief, "search-narrow", 0,
                )
            await _finalize_turn(belief, session_id, result.response)
            await save_working_memory(belief)
            return (
                ChatResponse(
                    response=result.response,
                    tools_called=getattr(result, "tools_called", []),
                    confidence=getattr(result, "confidence", 0.9),
                    messages=getattr(result, "messages", []),
                ),
                belief, "relative-cheaper", 0,
            )
        # No budget anchor yet → ask for it (targeted), and reuse the narrowing
        # capture machinery so the next "80 mil" answer lands on budget_max.
        belief.awaiting = "search_narrow:budget_max"
        resp = "Para mostrarte las más económicas, ¿cuál es tu presupuesto máximo aproximado?"
        belief.last_bot_message = resp
        belief.consecutive_failures = 0
        await save_working_memory(belief)
        return (
            ChatResponse(response=resp, tools_called=[], confidence=0.9),
            belief, "relative-cheaper-ask-budget", 0,
        )

    # ── FAQ / knowledge question fast-route ───────────────────────────────────
    # An informational question (requisitos, garantía, contrato, seña, expensas,
    # "cómo es el tema para alquilar", …) must be answered by the knowledge
    # specialist — NEVER re-run as a property search just because it mentions
    # "alquilar/comprar". Supports MULTIPLE questions in one message: the specialist
    # returns one self-contained answer per question (response.messages), delivered
    # as sequential WhatsApp bubbles by the adapter.
    if (_is_faq_question(message)
            and not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling_"))
            and "scheduling" not in (getattr(belief, "active_intents", None) or set())):
        _nq = _count_questions(message)
        logger.info(f"[Router] ❓ FAQ route → knowledge ({_nq}q) for {session_id}: {message[:80]}")
        from app.agents.s2_agent import process_message_with_specialist
        from app.agents.coordinator import SPECIALISTS
        _faq_ctx = context_prompt or ""
        if _nq >= 2:
            _faq_ctx = (
                f"[MÚLTIPLES PREGUNTAS] El usuario hizo {_nq} preguntas distintas en un "
                f"solo mensaje. Respondé CADA una por separado en el campo `mensajes` del "
                f"JSON (una entrada por pregunta, en orden, autocontenidas).\n" + _faq_ctx
            )
        result = await process_message_with_specialist(
            message=message,
            session_id=session_id,
            context_prompt=_faq_ctx,
            specialist=SPECIALISTS["knowledge"],
            recent_messages=recent_messages,
        )
        _update_belief_from_result(belief, result)
        _resp_text = result.response
        _handoff = await _finalize_and_check_handoff(
            belief, session_id, _resp_text, getattr(result, "tools_called", []),
        )
        if _handoff is not None:
            _resp_text, _ = _handoff
        await save_working_memory(belief)
        return (
            ChatResponse(
                response=_resp_text,
                tools_called=getattr(result, "tools_called", []),
                confidence=getattr(result, "confidence", 0.9),
                messages=getattr(result, "messages", []),
            ),
            belief, "faq-knowledge", 0,
        )

    # ── Search refinement fast-path (FIX 4/5) ─────────────────
    # After a search, a message with new criteria and no scheduling signal is a
    # refinement — re-run the search. This preempts the spurious-scheduling bug
    # where "2 ambientes, zona centro" or "tengo 35 millones" got routed to the
    # scheduling flow ("¿qué día querés coordinar la visita?").
    if not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling_")) \
            and _is_search_refinement(belief, message):
        logger.info(f"[Router] 🔁 Search refinement for {session_id}: {message[:80]}")
        # A refinement is a topic switch away from any stale scheduling persistence.
        _clear_scheduling_state(belief)
        await clear_saved_state(session_id)
        # Deterministic, belief-driven search: guarantees the exact filters (single type,
        # bedrooms, zone, budget). The LLM can't mix types or drop filters.
        result = await _run_belief_search(belief)
        _update_belief_from_result(belief, result)
        # Too-broad guard: if the refined search is still > threshold and a criterion
        # is missing, ask for one more instead of dumping the list.
        _narrow = (
            _maybe_narrow_search(belief)
            if "search_properties" in (getattr(result, "tools_called", []) or [])
            else None
        )
        if _narrow:
            _ntext, _nfield = _narrow
            belief.awaiting = f"search_narrow:{_nfield}"
            belief.last_bot_message = _ntext
            belief.consecutive_failures = 0
            await save_working_memory(belief)
            return (
                ChatResponse(response=_ntext, tools_called=getattr(result, "tools_called", []), confidence=0.9),
                belief, "search-narrow", 0,
            )
        _handoff = await _finalize_and_check_handoff(
            belief, session_id, result.response, getattr(result, "tools_called", []),
        )
        if _handoff is not None:
            _resp_text, _resp_tools = _handoff
        else:
            _resp_text, _resp_tools = result.response, getattr(result, "tools_called", [])
        await save_working_memory(belief)
        return (
            ChatResponse(
                response=_resp_text,
                tools_called=_resp_tools,
                confidence=getattr(result, "confidence", 0.9),
                messages=getattr(result, "messages", []),
            ),
            belief, "search-refinement", 0,
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

    # ── Visit intent on a selected property → enter the scheduling flow ──
    # "quiero verlo en persona", "coordinar una visita", etc. with a property already
    # selected must route to the SCHEDULING specialist (which never asks for a phone and
    # collects one slot at a time) AND establish scheduling state so the NEXT turn's
    # day/time/name get captured by update_belief (its extraction is gated on an active
    # scheduling context). Without this the message was misrouted to `search`: the wrong
    # specialist asked for a phone, scheduling was never established, and the booking
    # later failed with empty slots ("⚠️ Faltan datos…").
    if (getattr(belief, "selected_property_id", None)
            and not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling_"))
            and "scheduling" not in (belief.active_intents or set())
            and (_SCHEDULING_VERB.search(message) or _VISIT_PHRASE.search(message))
            and not _PHOTO_DETAIL_INTENT.search(message)
            and not _is_search_refinement(belief, message)):
        logger.info(f"[Router] 🗓️ Visit intent → scheduling for {session_id}: {message[:80]}")
        belief.active_intents.add("scheduling")
        _capture_day_time(belief, message)  # capture any day/time bundled in this message
        _capture_name(belief, message)      # capture name bundled in this message ("soy X")
        await save_specialist_state(session_id, "scheduling")
        from app.agents.s2_agent import process_message_with_specialist
        from app.agents.coordinator import SPECIALISTS, _build_scheduling_context as _bsc_vi
        sched_context = _bsc_vi(belief) + "\n" + (context_prompt or "")
        result = await process_message_with_specialist(
            message=message,
            session_id=session_id,
            context_prompt=sched_context,
            specialist=SPECIALISTS["scheduling"],
            recent_messages=recent_messages,
        )
        _update_belief_from_result(belief, result)
        await _finalize_turn(belief, session_id, result.response)
        resp_text, _label = await _maybe_confirm_or_pass(belief, result, session_id)
        # If the specialist's question didn't map to a concrete slot, advance to the
        # next one we still need so the next turn enters the awaiting fast-path.
        if not (getattr(belief, "awaiting", None) and str(belief.awaiting).startswith("scheduling")):
            belief.awaiting = _next_scheduling_slot(belief) or "scheduling_day"
        await save_working_memory(belief)
        return (
            ChatResponse(response=resp_text, tools_called=getattr(result, "tools_called", []),
                         confidence=getattr(result, "confidence", 0.9)),
            belief, "visit-intent::scheduling", 0,
        )

    # ── Cross-turn specialist persistence ─────────────────────
    # If the scheduling specialist was active last turn, keep it active
    saved = await get_saved_state(session_id)
    if saved and saved.active_specialist == "scheduling":
        # Check if user is switching topics away from scheduling
        topic_switch_kw = r"\b(busco|quiero|necesito|buscando|me interesa|mostrame|propiedades|lista|requisitos|garantía|precio|alquilar|comprar)\b"
        if not re.search(topic_switch_kw, message.lower().strip()):
            # Capture any day/time + name the user gave in this turn.
            _capture_day_time(belief, message)
            _capture_name(belief, message)
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

            # ── Anti-fabrication guard ──────────────────────────────────
            # The LLM specialist sometimes CLAIMS it booked ("Te confirmo la visita
            # para #10…") without actually calling schedule_visit. Never surface that:
            #  • if we have all slots → book deterministically for real;
            #  • otherwise → replace the fake claim with an honest ask for the next slot.
            _llm_booked = bool(result.tools_called and "schedule_visit" in result.tools_called)
            if not _llm_booked and _FAKE_BOOKING.search(result.response or ""):
                if (belief.scheduling_name and belief.scheduling_day
                        and belief.scheduling_time and belief.selected_property_id):
                    from app.tools.v2.schedule_visit import schedule_visit as _sv2
                    _btxt = await _sv2(
                        property_id=belief.selected_property_id,
                        nombre=belief.scheduling_name,
                        dia=belief.scheduling_day,
                        horario=belief.scheduling_time,
                    )
                    _bad = any(m in _btxt for m in (
                        "⚠️", "No pude", "Los domingos", "El horario de las",
                        "Tuve un problema", "fuera de", "está ocupado", "Faltan datos", "me falta",
                    ))
                    belief.last_tool_called = "schedule_visit"
                    if not _bad:
                        _clear_scheduling_state(belief)
                        await clear_saved_state(session_id)
                    await save_working_memory(belief)
                    return (
                        ChatResponse(response=_btxt, tools_called=["schedule_visit"], confidence=0.95),
                        belief, "specialist::anti-fake-booked", round((time.perf_counter() - t0) * 1000, 2),
                    )
                # Missing a slot → honest ask instead of a fake confirmation.
                _slot = _next_scheduling_slot(belief) or "scheduling_day"
                belief.awaiting = _slot
                _q = {
                    "scheduling_property": "¿Sobre cuál de las propiedades querés coordinar la visita?",
                    "scheduling_name": "Genial 👍 ¿A nombre de quién registro la visita?",
                    "scheduling_day": "¿Qué día te quedaría bien para la visita?",
                    "scheduling_time": "¿En qué horario te viene mejor?",
                }.get(_slot, "¿Qué día y horario te quedan bien para la visita?")
                belief.scheduling_loop_count += 1  # feed the cross-turn escape hatch
                belief.last_bot_message = _q
                await save_working_memory(belief)
                return (
                    ChatResponse(response=_q, tools_called=[], confidence=0.9),
                    belief, "specialist::anti-fake-reask", round((time.perf_counter() - t0) * 1000, 2),
                )

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

    # ── Coordinator: pure LLM routing ──────────────────────────────────
    # Always delegate to the coordinator — the LLM picks the right specialist.
    # Add scheduling context when scheduling is active so the specialist has slot info.
    from app.agents.coordinator import _build_scheduling_context as _bsc_fb, SPECIALISTS
    full_context = context_prompt or ""
    # Capture day/time from scheduling messages that bundle them ("el viernes a las 10").
    if getattr(belief, "awaiting", None) and str(belief.awaiting or "").startswith("scheduling_"):
        _capture_day_time(belief, message)
    elif "scheduling" in (getattr(belief, "active_intents", None) or set()):
        _capture_day_time(belief, message)
    _has_scheduling_state = any([
        getattr(belief, "scheduling_name", None),
        getattr(belief, "scheduling_day", None),
        getattr(belief, "scheduling_time", None),
        getattr(belief, "awaiting", None) and belief.awaiting.startswith("scheduling_"),
    ])
    if _has_scheduling_state:
        full_context = _bsc_fb(belief) + "\n" + full_context

    result, specialist_name = await coordinate(message, session_id, full_context, recent_messages=recent_messages)

    if result.tools_called and "schedule_visit" in result.tools_called:
        _failed = any(m in result.response for m in (
            "⚠️", "No pude", "Los domingos", "El horario de las",
            "Tuve un problema", "fuera de", "está ocupado", "Faltan datos",
        ))
        if not _failed:
            _clear_scheduling_state(belief)
            await clear_saved_state(session_id)
        else:
            await save_specialist_state(session_id, "scheduling")
    elif _has_scheduling_state:
        await save_specialist_state(session_id, "scheduling")

    latency = (time.perf_counter() - t0) * 1000
    _update_belief_from_result(belief, result)
    # Too-broad guard: if this search returned > threshold results and a criterion is
    # still missing, ask for one more instead of showing a huge list.
    _narrow = (
        _maybe_narrow_search(belief)
        if "search_properties" in (result.tools_called or [])
        else None
    )
    if _narrow:
        _ntext, _nfield = _narrow
        belief.awaiting = f"search_narrow:{_nfield}"
        belief.last_bot_message = _ntext
        belief.consecutive_failures = 0
        await save_working_memory(belief)
        return (
            ChatResponse(response=_ntext, tools_called=result.tools_called, confidence=0.9),
            belief, "search-narrow", round(latency, 2),
        )
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
                    ids = re.findall(r"(?:ID:|\[)(\d+)", result_text)
                    belief.last_search_ids = [int(x) for x in ids]
                    # Build a rich lookup string including type, price, and TITLE
                    # Format: "  [1] Departamento en Centro — Alquiler $85,000/mes\n       1 dorm | 45m² | Depto 2 amb céntrico"
                    result_lines = result_text.split("\n")
                    summaries = []
                    for i, line in enumerate(result_lines):
                        m = re.match(r"\s*\[(\d+)\]\s+(.+?)\s+(?:—|--)\s+(.+?)$", line)
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
                    elif belief.last_search_ids and result_text:
                        # Fallback: store raw result so _property_type_from_context
                        # can still scan "[ID] TypeName" even when the summary
                        # regex didn't match (e.g. tool uses "--" instead of "—").
                        belief.last_search_context = result_text[:3000]

                    # Zero or fallback result zone clearing.
                    # When the exact search returned nothing (ids empty) OR the result is a
                    # fallback ("No encontré…" header with other-zone/different-criteria props),
                    # clear zone so the next turn searches broadly rather than hitting the same
                    # dead-end zone again.
                    # E2 fix: also detect fallback responses (start with "No encontr")
                    # — previously they left last_search_ids non-empty (fallback IDs) so the
                    # zone was never cleared, causing the same failed search to repeat.
                    _result_is_fallback = bool(
                        re.match(r"No\s+encontr", result_text.lstrip(), re.IGNORECASE)
                    )
                    if (_result_is_fallback or not belief.last_search_ids) and belief.zone:
                        cleared_zone = belief.zone
                        belief.zone = None
                        belief.pending_offer = (
                            f"mostrar {belief.property_type or 'propiedades'} "
                            + (f"de {belief.operation} " if belief.operation else "")
                            + f"disponibles en otras zonas (no hay resultados exactos en {cleared_zone})"
                            + " — llamar search_properties sin parámetro zona"
                        )
                    elif belief.last_search_ids and not _result_is_fallback:
                        # Exact results found — clear any stale zone-fallback offer
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
                    # Record this property in the viewed-in-detail memory so an anaphoric
                    # reference ("me interesa más la casa") resolves to what the user saw.
                    _vid = belief.selected_property_id
                    if _vid:
                        _vtitle = _extract_detail_title(result_text) or f"propiedad #{_vid}"
                        _vtipo = _classify_title_type(_vtitle)
                        belief.viewed_properties = [
                            v for v in belief.viewed_properties if v.get("id") != _vid
                        ]
                        belief.viewed_properties.append(
                            {"id": _vid, "tipo": _vtipo, "titulo": _vtitle}
                        )
                        belief.viewed_properties = belief.viewed_properties[-10:]

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

    # ── LLM self-correction: apply belief fixes the model flagged this turn ──
    _apply_belief_corrections(belief, getattr(result, "belief_corrections", None))


# Fields the LLM is allowed to correct, with their validators/coercers.
_CORRECTABLE_FIELDS: dict[str, str] = {
    "operation": "operation",
    "property_type": "str",
    "zone": "str",
    "budget_max": "float_pos",
    "bedrooms_min": "int_small",
    "scheduling_day": "str",
    "scheduling_time": "str",
    "scheduling_name": "str",
}


def _apply_belief_corrections(belief, corrections: "dict | None") -> None:
    """Apply LLM-flagged corrections to the belief state, with strict validation.

    The LLM emits these in the "correcciones" field when the regex-extracted state
    contradicts what the user actually said (typos, slang, context). This is the
    self-correction safety net for the unidirectional regex→belief pipeline.

    Only whitelisted fields are accepted, each value is coerced + bounds-checked, and
    anything invalid is silently dropped. Never raises.
    """
    if not corrections or not isinstance(corrections, dict):
        return
    for raw_key, raw_val in corrections.items():
        key = str(raw_key).strip()
        kind = _CORRECTABLE_FIELDS.get(key)
        if kind is None:
            continue
        if raw_val in (None, "", "null", "None"):
            continue
        try:
            if kind == "operation":
                val = str(raw_val).strip().lower()
                if val in ("alquilar", "rentar"):
                    val = "alquiler"
                if val in ("comprar", "compra"):
                    val = "venta"
                if val not in ("alquiler", "venta"):
                    continue
            elif kind == "float_pos":
                val = float(raw_val)
                if not (0 < val <= 1e12):
                    continue
            elif kind == "int_small":
                val = int(float(raw_val))
                if not (0 <= val <= 20):
                    continue
            else:  # "str"
                val = str(raw_val).strip()
                if not val or len(val) > 120:
                    continue
        except (ValueError, TypeError):
            continue
        _old = getattr(belief, key, None)
        if _old == val:
            continue
        setattr(belief, key, val)
        logger.info(f"[Router] 🔧 LLM self-correction: {key}: {_old!r} → {val!r}")


# ═══════════════════════════════════════════════════════════════════════
# WhatsApp Inbox — Conversation persistence wrapper
# ═══════════════════════════════════════════════════════════════════════
# Wraps route_message() to persist the turn to the database after
# every successful bot response.  v2_adapter.py calls this instead of
# route_message() directly.

from app.db.session import async_session_factory
from app.services.conversation_service import upsert_conversation, save_turn


# ── Response guard (LLM critic over the candidate response) ───────────────────
# Router labels whose responses are LLM-generated and safe to review/regenerate.
# Deterministic shortcuts (pre-llm::*, awaiting::*, search-narrow*, select-*, …) and
# stateful booking flows (scheduling) are intentionally NOT guarded.
_GUARDABLE_LABELS = {
    "search", "knowledge", "rapport", "negotiator",
    "faq-knowledge", "search-refinement",
}
_GUARD_FALLBACK_MSG = (
    "Disculpá, no te entendí del todo 🤔. ¿Podrías reformular tu mensaje de otra "
    "forma así te ayudo mejor?"
)


def _recent_ctx_str(recent_messages: list) -> str:
    """Compact the last few turns into a short text block for the guard."""
    if not recent_messages:
        return ""
    out = []
    for m in recent_messages[-4:]:
        role = "Usuario" if m.get("role") == "user" else "Bot"
        content = str(m.get("content", "")).strip().replace("\n", " ")
        if content:
            out.append(f"{role}: {content[:160]}")
    return "\n".join(out)


async def _apply_response_guard(
    message: str, session_id: str, response: ChatResponse,
    belief: ConversationBeliefState, router_label: str,
) -> "tuple[ChatResponse, str]":
    """Review an LLM-generated response; if it doesn't address the user's request,
    re-route to the correct specialist (up to 2 attempts). After 2 failed re-routes,
    return an honest fallback asking the user to rephrase.

    Returns (response, router_label) — unchanged when the guard passes or is skipped.
    Fail-open: any error leaves the original response untouched.
    """
    # ── Gating ────────────────────────────────────────────────────────────────
    if os.getenv("RESPONSE_GUARD_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return response, router_label
    if router_label not in _GUARDABLE_LABELS:
        return response, router_label
    if "schedule_visit" in (response.tools_called or []):
        return response, router_label
    if not (response.response and response.response.strip()):
        return response, router_label

    try:
        from app.agents.response_guard import evaluate_response
        from app.agents.coordinator import SPECIALISTS
        from app.agents.s2_agent import process_message_with_specialist

        # Rebuild the context the specialists need (same as _route_message_inner).
        context_prompt = build_context_prompt(belief)
        recent_messages: list = []
        try:
            from app.core.memory import MemoryManager
            _raw = await MemoryManager().get_recent_messages(session_id, limit=6)
            recent_messages = _strip_messages(_raw)
        except Exception:
            recent_messages = []
        recent_ctx = _recent_ctx_str(recent_messages)

        verdict = await evaluate_response(
            message, response.response, response.tools_called or [], recent_ctx,
        )
        if verdict.get("ok", True):
            return response, router_label

        cur = response
        attempts = 0
        while not verdict.get("ok", True) and attempts < 2:
            attempts += 1
            esp_name = verdict.get("especialista") or "knowledge"
            spec = SPECIALISTS.get(esp_name)
            if spec is None:
                break
            logger.info(
                f"[Guard] reroute #{attempts} → {esp_name} for {session_id}: "
                f"{verdict.get('problema')}"
            )
            hint = (
                "[REVISIÓN INTERNA] Tu respuesta anterior fue marcada como incorrecta: "
                f"{verdict.get('problema') or 'no atendía lo que el usuario pidió'}. "
                "Volvé a responder atendiendo EXACTAMENTE el pedido del usuario, sin "
                "mencionar esta revisión.\n"
            )
            result = await process_message_with_specialist(
                message=message,
                session_id=session_id,
                context_prompt=hint + (context_prompt or ""),
                specialist=spec,
                recent_messages=recent_messages,
            )
            _update_belief_from_result(belief, result)
            cur = ChatResponse(
                response=result.response,
                tools_called=getattr(result, "tools_called", []),
                confidence=getattr(result, "confidence", 0.9),
                messages=getattr(result, "messages", []),
            )
            verdict = await evaluate_response(
                message, cur.response, cur.tools_called or [], recent_ctx,
            )

        if not verdict.get("ok", True):
            # 2 re-routes still failed → honest fallback asking to rephrase.
            logger.info(f"[Guard] {attempts} reroutes failed → fallback for {session_id}")
            belief.last_bot_message = _GUARD_FALLBACK_MSG
            belief.consecutive_failures = (getattr(belief, "consecutive_failures", 0) or 0) + 1
            return (
                ChatResponse(response=_GUARD_FALLBACK_MSG, tools_called=[], confidence=0.4),
                "guard::fallback",
            )

        belief.last_bot_message = cur.response
        logger.info(f"[Guard] corrected response for {session_id} after {attempts} reroute(s)")
        return cur, f"guard::corrected:{verdict.get('especialista') or 'knowledge'}"
    except Exception as e:
        logger.warning(f"[Guard] _apply_response_guard failed (fail-open): {e}")
        return response, router_label


async def route_message_with_persistence(
    message: str, session_id: str, phone: str = ""
) -> tuple:
    """Call route_message() and persist the turn to DB on success."""
    result = await route_message(message, session_id, phone)
    response, belief, router_label, latency_ms = result

    # ── Response guard: review LLM-generated responses, re-route if wrong ──────
    try:
        _new_resp, _new_label = await _apply_response_guard(
            message, session_id, response, belief, router_label,
        )
        if _new_resp is not response:
            response = _new_resp
            router_label = _new_label
            await save_working_memory(belief)
            result = (response, belief, router_label, latency_ms)
    except Exception as _ge:
        logger.warning(f"[Guard] wrapper failed (fail-open): {_ge}")

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
