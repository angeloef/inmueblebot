"""V3 Understanding Engine (Phase 3).

Single-pass schema-guided LLM architecture:
  1. Safety gates (regex, O(1)) — emergency / human-request / out-of-scope / /reset
  2. One structured OpenAI call (strict json_schema, gpt-5.4-mini via LLMRole.SYNTH)
     returning { belief_delta, intent, action, tool_calls, response_plan, confidence }
  3. Deterministic tool execution layer (tools listed in engine output, validated, run)
  4. Optional synthesis call if tools ran but engine gave no response_plan
  5. Optional gated quality judge (guard.py) + one targeted regen on fail

LLM call budget per turn (median ≤3):
  - Call 1 (always): engine structured call
  - Call 2 (conditional): response synthesis when tools ran + no response_plan
  - Call 3 (conditional, gated): rubric judge on low-confidence/critical turns,
    plus at most one targeted regeneration on a judge fail
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

_SAFE_CLARIFY_ES = (
    "Disculpá, no pude procesar tu mensaje correctamente. "
    "¿Podés contarme qué tipo de propiedad estás buscando y si querés alquilar o comprar?"
)

# Sent as a separate message right after a property's photos, to keep the flow moving.
_PHOTO_CTA_ES = (
    "¿Te gustó la propiedad? Podemos coordinar una visita para que la veas en persona, "
    "o si preferís te muestro otra opción de la lista. ¿Cómo seguimos?"
)

# Firm-but-polite nudge for an abusive message that is still UNDER the escalation
# threshold (a plain off-topic message gets _OUT_OF_SCOPE_RESPONSE instead).
_ABUSE_REDIRECT_ES = (
    "Entiendo que puedas estar molesto, pero te pido que mantengamos el respeto. "
    "Con gusto te ayudo con tu búsqueda: ¿qué tipo de propiedad estás buscando?"
)

# One-time message when the 5-strike off-topic/abuse escalation fires (bot pauses).
_ABUSE_HANDOFF_ES = (
    "Para poder ayudarte mejor, voy a derivar tu consulta a uno de nuestros asesores, "
    "que se va a comunicar con vos a la brevedad. ¡Gracias por tu comprensión!"
)


def _daily_cap_message(agency: str) -> str:
    """One-time professional notice when a user hits the daily message cap."""
    de_agencia = f" de {agency}" if agency else ""
    return (
        "Por hoy alcanzaste el límite de mensajes de este asistente automático. "
        f"Un asesor{de_agencia} va a revisar tu conversación y se va a comunicar con vos "
        "a la brevedad para ayudarte personalmente. ¡Gracias por tu paciencia! 🙌"
    )

# Max photos to deliver per request (WhatsApp sends one image per message).
_MAX_PHOTOS = 4

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
        criterios = dict(belief.search_criteria)
        # Surface bedroom range so a refinement re-search keeps it (#25).
        if getattr(belief, "bedrooms_max", None) is not None:
            criterios["dormitorios_máx"] = belief.bedrooms_max
        if getattr(belief, "bedrooms_match", None):
            criterios["dormitorios_modo"] = belief.bedrooms_match
        state["criterios"] = criterios
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
                bedrooms_max=getattr(belief, "bedrooms_max", None),
                bedrooms_match=getattr(belief, "bedrooms_match", None),
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

# Structural marker emitted by format_appointment_confirmation on real DB commit.
# Presence in the schedule_visit result string is the SOLE source of truth for
# booking_succeeded. No other substring check is used.
_BOOKING_SUCCESS_MARKER = "<!--CONFIRMED:"


# Tools that operate on a specific property — if the model omitted property_id, fill
# it from the resolved selection so a dropped id can't break details/photos/booking.
_PROPERTY_ID_TOOLS = frozenset({"get_property_details", "get_property_images", "schedule_visit"})

_SCHEDULING_AWAITING_SLOTS = ("scheduling_day", "scheduling_time", "scheduling_confirm")


def _apply_new_search_reset(belief, turn) -> None:
    """Plan #3: a fresh search clears the prior selection and in-flight scheduling slots.

    Called from step 6 when the engine requests search_properties this turn. Without
    it, a property-scoped follow-up ("mostrame fotos") backfills the OLD
    selected_property_id and a half-finished booking leaks across searches — the user
    can see or book the wrong unit. ``scheduling_name`` is preserved (the person's name
    carries across searches). The ordinal backstop is intentionally NOT applied by the
    caller on a new search (an ordinal like "la primera" refers to the new list).
    """
    belief.selected_property_id = turn.selected_property_id  # usually None → cleared
    if getattr(belief, "awaiting", None) in _SCHEDULING_AWAITING_SLOTS:
        belief.awaiting = None
        belief.pending_scheduling = False
        belief.scheduling_day = ""
        belief.scheduling_time = ""


def _clear_stale_scheduling_awaiting(belief, turn, prev_last_intent) -> None:
    """Plan #13: drop a scheduling `awaiting` the user has clearly abandoned.

    `awaiting` has no TTL. If the user started a booking ("esperando: scheduling_day")
    then changed the subject, [ESTADO] keeps telling the LLM it's waiting for that slot.
    Require TWO consecutive off-topic turns (this turn's intent and the previous one are
    both non-scheduling) before clearing, so a single FAQ interruption mid-booking does
    NOT reset the flow (#10/§3.6 keep that case alive). Never touches scheduling_name.
    """
    if getattr(turn, "intent", None) == "scheduling":
        return
    awaiting = getattr(belief, "awaiting", None)
    if not (awaiting and str(awaiting).startswith("scheduling_")):
        return
    if prev_last_intent is None or prev_last_intent == "scheduling":
        return
    belief.awaiting = None
    belief.pending_scheduling = False


def _persist_schedule_args(belief, args: dict) -> None:
    """Copy a schedule_visit call's day/time/name into belief.scheduling_* (plan #10).

    Only overwrites a field when the call actually carried a non-empty value, so a
    partial re-emission (e.g. property_id + dia only) never wipes a previously
    captured horario/nombre.
    """
    dia = (args.get("dia") or "").strip()
    horario = (args.get("horario") or "").strip()
    nombre = (args.get("nombre") or "").strip()
    if dia:
        belief.scheduling_day = dia
    if horario:
        belief.scheduling_time = horario
    if nombre:
        belief.scheduling_name = nombre


def _persist_scheduling_slots_from_message(belief, turn, message: str) -> None:
    """On a scheduling turn, capture day/time the user just gave into the belief (plan #10).

    The engine path never wrote slot VALUES (only `awaiting`), so a day given early in
    a long booking flow was forgotten once it slid out of the history window. Running
    the existing concrete-value extractors here persists them turn-by-turn. Only stores
    a value when the extractor finds a concrete one; never clears on a miss.
    """
    if getattr(turn, "intent", None) != "scheduling" or not message:
        return
    try:
        from app.core.state_transitioner import extract_scheduling_day, extract_scheduling_time
        day = extract_scheduling_day(message)
        if day:
            belief.scheduling_day = day
        clock = extract_scheduling_time(message)
        if clock:
            belief.scheduling_time = clock
    except Exception:
        pass


async def _execute_tools(turn, belief) -> tuple[list[str], list[str], bool, bool]:
    """Execute tool_calls from engine output deterministically.

    Returns (tools_used, tool_results, any_ran, booking_succeeded).
    booking_succeeded is True only when schedule_visit returns a string containing
    _BOOKING_SUCCESS_MARKER (the structural marker from format_appointment_confirmation).
    Each tool is validated before execution. Unknown/invalid tools are skipped.
    For property-scoped tools, a missing/zero property_id is backfilled from
    belief.selected_property_id (set by the engine or the ordinal backstop).
    execute_tool never raises (returns error string).
    Tenant scope is already set via ContextVar from step 0.
    """
    from app.tools.v2.registry import execute_tool, validate_tool_args
    from app.agents.schemas import CSStructuredToolCall

    tools_used: list[str] = []
    tool_results: list[str] = []
    any_ran = False
    booking_succeeded = False
    selected_id = getattr(belief, "selected_property_id", None)

    for i, tc in enumerate(turn.tool_calls or []):
        args = tc.parsed_args()
        if tc.name in _PROPERTY_ID_TOOLS and not args.get("property_id") and selected_id:
            args = {**args, "property_id": selected_id}
        ok, err = validate_tool_args(tc.name, args)
        if not ok:
            logger.debug("[V3] Skipping tool {}: {}", tc.name, err)
            continue
        # Persist the booking slots the LLM reconstructed (plan #10). The model's
        # schedule_visit args are the best available day/time/name; storing them on
        # the belief makes the NEXT turn independent of the history window and revives
        # the FSM T-7 availability pre-check (which reads belief.scheduling_*).
        if tc.name == "schedule_visit":
            _persist_schedule_args(belief, args)
        try:
            call = CSStructuredToolCall(id=f"call_{i}", name=tc.name, arguments=args)
            result = await execute_tool(call)
            result_str = str(result)
            tools_used.append(tc.name)
            tool_results.append(result_str)
            any_ran = True
            # Structural booking success check — only schedule_visit can emit this marker
            if tc.name == "schedule_visit" and _BOOKING_SUCCESS_MARKER in result_str:
                booking_succeeded = True
        except Exception as exc:
            logger.warning("[V3] Tool {} error: {}", tc.name, str(exc))
            tool_results.append(f"Error: {exc}")
            tools_used.append(tc.name)

    return tools_used, tool_results, any_ran, booking_succeeded


# ── Search-context persistence ────────────────────────────────────────────────

# Matches both the normalized "ID:7" format and the legacy "[7]" bracket format so
# ordinal resolution keeps working across the format change.
_SEARCH_ID_RE = re.compile(r"(?:ID:|\[)(\d+)")


_ORDINAL_PATTERNS: list[tuple] = [
    (re.compile(r"\b(primer[oa]?|primera)\b", re.IGNORECASE), 0),
    (re.compile(r"\b(segund[oa])\b", re.IGNORECASE), 1),
    (re.compile(r"\b(tercer[oa]?|tercera)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(cuart[oa])\b", re.IGNORECASE), 3),
    (re.compile(r"\b(quint[oa])\b", re.IGNORECASE), 4),
]
_LAST_ORDINAL_RE = re.compile(r"\b(últim[oa]|ultim[oa])\b", re.IGNORECASE)

# Per-property header line from _format_properties_list: "  ID:12 — Departamento en
# Centro — $250.000/mes". These compact lines (id + tipo + zona + precio) are the
# clean comparative material for follow-ups; the secondary "2 dorm | …" spec lines and
# any header/footer prose are dropped (plan #21). Cap the count to bound state size.
_SEARCH_SUMMARY_LINE_RE = re.compile(r"^ID:\d+\s+—\s+.+—.+$")
_MAX_SUMMARY_LINES = 12


def _resolve_ordinal_to_id(message: str, last_search_ids: list) -> int | None:
    """Map a positional reference ("la primera", "el tercero", "la última") to a
    concrete property id from the previous search. Structural mapping only — no
    understanding. Returns None when there is no ordinal or no prior results.
    """
    if not last_search_ids:
        return None
    msg = message or ""
    if _LAST_ORDINAL_RE.search(msg):
        return last_search_ids[-1]
    for rx, idx in _ORDINAL_PATTERNS:
        if rx.search(msg) and idx < len(last_search_ids):
            return last_search_ids[idx]
    return None


def _compact_search_summary(res: str) -> str:
    """Reduce a formatted search result to one compact line per property (plan #21).

    Keeps the "ID:N — Tipo en Zona — $precio" header lines (whole, never truncated),
    drops the secondary spec lines and any header/footer prose, and caps the count so
    the stored state JSON stays small. Falls back to a char-capped prefix if the result
    isn't in the expected format (e.g. a no-results or progressive-narrowing message).
    """
    lines = [ln.strip() for ln in (res or "").splitlines()]
    summary = [ln for ln in lines if _SEARCH_SUMMARY_LINE_RE.match(ln)]
    if summary:
        return "\n".join(summary[:_MAX_SUMMARY_LINES])
    return (res or "")[:1200]


def _persist_search_context(belief, tools_used: list[str], tool_results: list[str]) -> None:
    """Store the latest search_properties result on the belief.

    Lets the NEXT turn resolve ordinal/positional references ("la primera", "el 3")
    to a concrete property id via [ESTADO].ultima_busqueda, and answer follow-ups
    ("cuál tiene más ambientes") from the stored list. Without this the engine has no
    way to map a position to an id. Fails silently — never breaks a turn.
    """
    try:
        for name, res in zip(tools_used, tool_results):
            if name != "search_properties" or not res:
                continue
            ids = [int(m) for m in _SEARCH_ID_RE.findall(res)]
            belief.last_search_ids = ids
            belief.last_search_count = len(ids)
            # Store compact one-line-per-ID summaries instead of a char-truncated blob
            # (plan #21): cheaper tokens, never cuts an entry mid-line, and gives the
            # model clean material for comparative answers / descriptive selection.
            belief.last_search_context = _compact_search_summary(res)
            break
    except Exception:
        pass


# ── Marker stripper ───────────────────────────────────────────────────────────

_MARKER_STRIP_RE = re.compile(r"<!--CONFIRMED:.*?-->", re.DOTALL)


def _strip_markers(text: str) -> str:
    """Remove all <!--CONFIRMED:…--> markers from text before it reaches the user."""
    if not text or _BOOKING_SUCCESS_MARKER not in text:
        return text
    return _MARKER_STRIP_RE.sub("", text).strip()


# ── Synthesis from tool results (shared by must-surface + no-plan paths) ──────

# Tools whose TEXTUAL results must reach the user verbatim-ish — the engine's own
# placeholder prose ("Buscando...") is NOT authoritative; show the real data.
_DATA_TOOLS = frozenset({
    "search_properties", "get_property_details", "get_faq_answer",
    "get_my_appointments", "cancel_appointment", "reschedule_appointment",
    "knowledge_retrieval",  # RAG safety-net injection
})


def _is_about_shown_results(turn, belief) -> bool:
    """True when the turn is a follow-up about the JUST-SHOWN search results (plan #8).

    The model labels comparative/price questions about the visible list as
    intent==search; when ``last_search_context`` is populated the answer lives in the
    state, so the RAG safety-net must NOT inject FAQ/property chunks (they drown the
    real answer). Used to gate Step 7b.
    """
    return getattr(turn, "intent", None) == "search" and bool(belief.last_search_context)


def _recent_history_tail(belief, max_entries: int = 4) -> str:
    """Last few conversation lines for synthesis context (plan #7).

    ``belief.history`` already has the current ``user:`` message appended by run_turn
    before assembly, so drop that trailing entry — it is passed separately as the
    question. Returns the preceding ``max_entries`` lines joined, or "" if none.
    """
    history = list(belief.history or [])
    if history and history[-1].startswith("user: "):
        history = history[:-1]
    tail = history[-max_entries:]
    return "\n".join(tail)


async def _synthesize_from_results(belief, tool_results: list[str], user_message: str = "") -> str:
    """Compose a Spanish reply grounded in real tool results (LLM Call 2).

    Grounded in the user's actual question and the recent conversation tail (plan #7):
    without them the synthesizer only saw the tool dump + state and could answer the
    wrong question (e.g. a generic FAQ instead of the pet-policy that was asked).

    Returns "" on any failure so callers can fall back to the engine plan.
    """
    from app.agents.cs_llm_client import get_client, get_model, max_tokens_kwarg, LLMRole
    from app.core.response_parser import get_final_response_format, parse_llm_response

    if not tool_results:
        return ""
    try:
        compact = json.dumps(_compact_state(belief), ensure_ascii=False)
        tool_context = "\n".join(f"[{i+1}] {r}" for i, r in enumerate(tool_results))
        history_tail = _recent_history_tail(belief)
        question = (user_message or "").strip()
        user_parts: list[str] = []
        if question:
            user_parts.append(f"Pregunta del usuario:\n{question}")
        if history_tail:
            user_parts.append(f"Conversación reciente:\n{history_tail}")
        user_parts.append(f"Resultados de herramientas:\n{tool_context}")
        user_parts.append(
            "Respondé la pregunta del usuario basándote SOLO en estos resultados."
            if question
            else "Respondé al usuario basándote en estos resultados."
        )
        synth_messages = [
            {
                "role": "system",
                "content": (
                    "Sos un asistente inmobiliario. "
                    "Usá los resultados de las herramientas para dar una respuesta clara y amigable al usuario. "
                    "Mostrá las propiedades o datos que devolvieron las herramientas; no los resumas a 'estoy buscando'. "
                    "Respondé SIEMPRE en español. Sé conciso y profesional."
                ),
            },
            {"role": "system", "content": f"[ESTADO]\n{compact}"},
            {"role": "user", "content": "\n\n".join(user_parts)},
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
            return text or ""
    except Exception as exc:
        logger.warning("[V3] Synthesis call failed: {}", str(exc))
    return ""


# ── Response assembly ─────────────────────────────────────────────────────────

async def _assemble_response(
    turn,
    belief,
    tool_results: list[str],
    any_ran: bool,
    tenant_id,
    booking_succeeded: bool = False,
    fsm_plan: list | None = None,
    tools_used: list[str] | None = None,
    user_message: str = "",
) -> tuple[str, dict, str]:
    """Build response_text and rich_content from engine output + tool results.

    Priority (with FSM override and anti-hallucination guard):
    0. FSM override (fsm_plan provided) — render it and return.
    0b. Anti-hallucination guard: if turn.action=="book_step" AND booking_succeeded
        is False → DISCARD any confirmation response_plan; emit safe gather message.
    0c. Must-surface: a text-data tool produced results → synthesize from the REAL
        results (LLM Call 2) instead of the engine's placeholder prose. Excludes the
        image flow and booking confirmations.
    1. Engine response_plan (non-empty) — used for clarify/smalltalk/photos/booking.
    2. Synthesis — tools ran but engine has no plan (fallback to 0c's helper).
    3. Safe default — action in clarify/smalltalk/handoff with no plan.

    Returns (response_text, rich_content, source) where source ∈
    {"verbatim","synthesis","plan","fsm"} (plan #14). Deterministic, already-formatted
    tool output is tagged "verbatim"; run_guard never regenerates a "verbatim" reply
    (an LLM rewrite reintroduces the price/format drift the verbatim path prevents).
    Strips <!--CONFIRMED:…--> markers from all text before returning.
    """
    rich: dict = {
        "images": [],
        "caption": "",
        "selected_property_id": belief.selected_property_id,
        "search_criteria": belief.search_criteria,
        "active_intents": list(belief.active_intents),
    }

    # ── Path 0: FSM override ───────────────────────────────────────────
    if fsm_plan:
        # Render FSM plan directly (same segment logic as Path 1)
        text_segs = [p for p in fsm_plan if isinstance(p, dict) and p.get("type") == "text"]
        if len(text_segs) == 1:
            return _strip_markers(text_segs[0].get("content", "")), rich, "fsm"
        if text_segs:
            segments_out = [{"type": p.get("type", "text"), "content": p.get("content", "")} for p in fsm_plan]
            rich["response_plan"] = segments_out
            combined = " ".join(s.get("content", "") for s in text_segs)
            return _strip_markers(combined), rich, "fsm"
        # Fallback: use first item if any
        if fsm_plan:
            first = fsm_plan[0]
            return _strip_markers(first.get("content", _SAFE_CLARIFY_ES)), rich, "fsm"

    # ── Path 0b: Anti-hallucination guard ─────────────────────────────
    # If the engine planned a book_step confirmation but schedule_visit did NOT
    # succeed (no <!--CONFIRMED: marker), STRUCTURALLY discard the confirmation
    # response_plan so no fake "Cita Agendada" reaches the user.
    action = getattr(turn, "action", None)

    # ── Path 0a-appt: surface appointment-management results verbatim ──
    # cancel/reschedule/get_my_appointments are NOT new bookings — their tool
    # output is already a user-ready confirmation/listing. Surface it BEFORE the
    # book_step anti-hallucination guard below: the model frequently mislabels
    # these turns as book_step, and the guard would then discard the real result
    # and reply "Estoy recopilando los detalles para tu visita" (plan #1).
    _APPT_MGMT_TOOLS = ("get_my_appointments", "cancel_appointment", "reschedule_appointment")
    if tools_used and tool_results:
        for _name, _res in zip(tools_used, tool_results):
            if _name in _APPT_MGMT_TOOLS and _res and not _res.startswith("Error:"):
                return _strip_markers(_res), rich, "verbatim"

    if action == "book_step" and not booking_succeeded:
        # Discard the engine's (possibly fabricated) confirmation response_plan. BUT
        # surface the REAL schedule_visit result — it carries the actual reason the
        # booking didn't complete (out-of-hours, slot taken + suggestions, a missing
        # field re-ask, or a handoff). In this branch the result never contains the
        # CONFIRMED marker, so it's always a safe non-confirmation message. Returning
        # it (instead of a generic "still gathering" reply) is what prevents the
        # ask-the-same-thing loop the user hit in the first manual test.
        if tools_used and tool_results:
            for _name, _res in zip(tools_used, tool_results):
                if _name == "schedule_visit" and _res and not _res.startswith("Error:"):
                    return _strip_markers(_res), rich, "verbatim"
        return (
            "Estoy recopilando los detalles para tu visita. "
            "¿Podés confirmarme el día y horario que preferís?"
        ), rich, "plan"

    # ── Path 0b-booked: surface the REAL confirmation on success ───────
    # Mirror of the failure guard above. When the booking SUCCEEDED, the
    # schedule_visit result is the only string carrying the actual date/time/
    # address (+ the <!--CONFIRMED:--> marker). The engine's response_plan is just
    # a short placeholder ("Listo, agendo tu visita") — if we let it win, the user
    # gets a dateless generic confirmation while the appointment really exists.
    # Surface the tool result instead (markers stripped before sending).
    if action == "book_step" and booking_succeeded and tools_used and tool_results:
        for _name, _res in zip(tools_used, tool_results):
            if _name == "schedule_visit" and _res and not _res.startswith("Error:"):
                return _strip_markers(_res), rich, "verbatim"

    # ── Path 0a2: requested-but-none-ran → targeted clarify ───────────
    # The engine asked for tools but EVERY one was skipped by validation (e.g. a
    # property-scoped tool with no property_id and no selection). any_ran is False
    # and there are no results at all, so the only thing left to render would be the
    # engine's ≤8-word placeholder ("Un momento, reviso eso.") — a dead end (plan #2).
    # Replace it with a question that actually moves the conversation forward.
    requested_names = {tc.name for tc in (turn.tool_calls or [])}
    if requested_names and not any_ran and not tool_results:
        if requested_names & _PROPERTY_ID_TOOLS and not getattr(belief, "selected_property_id", None):
            return (
                "¿De cuál propiedad querés que te muestre eso? "
                'Decime el ID o la posición en la lista (por ejemplo, "la primera").'
            ), rich, "plan"
        return _SAFE_CLARIFY_ES, rich, "plan"

    # ── Path 0b-photos: deterministic photo delivery ──────────────────
    # If get_property_images ran for a selected property, ALWAYS resolve and send the
    # images + a visit CTA — never gate this on the engine emitting an 'images'
    # segment (it does so inconsistently, which dropped photos entirely and left the
    # user waiting). This mirrors the verbatim-render philosophy used for search/details.
    if "get_property_images" in (tools_used or []) and belief.selected_property_id:
        photo_rich = await _build_photo_plan(belief, rich)
        if photo_rich is not None:
            # Return the CTA as response_text so the assistant turn is recorded in
            # history (the next "sí" then has context); delivery uses response_plan.
            return _PHOTO_CTA_ES, photo_rich, "plan"
        # No images resolved → fall through to a normal text reply.

    # ── Path 0b2: deterministic render for already-formatted data tools ──
    # search_properties and get_property_details produce user-ready output (Argentine
    # prices, normalized ID:N, progressive narrowing, structured card). Send it
    # VERBATIM — re-synthesizing through the LLM is what caused the list truncation,
    # price-format drift ($35,976 vs $35.976), and "claimed a filter that wasn't
    # applied" bugs. Skip when the photo flow is involved (handled in Path 1).
    # Ordered by specificity: if both ran in one turn, the detail card wins over the
    # list so the more specific intent isn't silently dropped.
    _VERBATIM_TOOLS = ("get_property_details", "search_properties")
    _has_image = "get_property_images" in (tools_used or []) or any(
        getattr(p, "type", None) == "images" for p in (turn.response_plan or [])
    )
    if tools_used and action != "book_step" and not _has_image:
        verbatim_text = ""
        for _tool in _VERBATIM_TOOLS:
            if _tool in tools_used:
                for _n, _r in zip(tools_used, tool_results):
                    if _n == _tool and _r and not _r.startswith("Error:"):
                        verbatim_text = _strip_markers(_r)
                        break
            if verbatim_text:
                break
        if verbatim_text:
            # Multi-intent turn (plan #9): a verbatim tool ran alongside another data
            # tool (e.g. "busco depto en el centro, ¿y qué requisitos piden?" →
            # search_properties + get_faq_answer). Returning only the verbatim block
            # silently drops the second answer. Synthesize the remaining non-verbatim
            # data results and append them so both intents are answered.
            other_results = [
                _r for _n, _r in zip(tools_used, tool_results)
                if _n in _DATA_TOOLS and _n not in _VERBATIM_TOOLS
                and _r and not _r.startswith("Error:")
            ]
            if other_results:
                tail = await _synthesize_from_results(belief, other_results, user_message)
                if tail:
                    return f"{verbatim_text}\n\n{tail}".strip(), rich, "verbatim"
            return verbatim_text, rich, "verbatim"

    # ── Path 0c: must-surface real tool data ──────────────────────────
    # When a text-data tool produced results, the user must SEE those results —
    # the engine's placeholder prose ("Buscando...") is not authoritative. Synthesize
    # from the real results instead of returning the engine's response_plan. Excludes
    # the image flow (handled in Path 1) and booking confirmations (action==book_step).
    plan = turn.response_plan or []
    has_image_seg = any(getattr(p, "type", None) == "images" for p in plan)
    requested = {tc.name for tc in (turn.tool_calls or [])}
    must_surface = (
        any_ran and tool_results
        and not has_image_seg
        and action != "book_step"
        and "get_property_images" not in requested
    )
    if must_surface:
        surfaced = await _synthesize_from_results(belief, tool_results, user_message)
        if surfaced:
            return surfaced, rich, "synthesis"
        # synthesis failed → fall through to the engine plan / safe default

    # ── Path 1: engine provided a response_plan ────────────────────────
    plan = turn.response_plan or []
    if plan:
        # Check if plan has image segments
        image_segs = [p for p in plan if p.type == "images"]
        text_segs = [p for p in plan if p.type == "text"]

        if image_segs and belief.selected_property_id:
            # Engine asked for photos via a plan segment (without a get_property_images
            # tool call). Deliver them the same deterministic way: images (no repeated
            # caption) + a single visit CTA.
            photo_rich = await _build_photo_plan(belief, rich)
            if photo_rich is not None:
                return _PHOTO_CTA_ES, photo_rich, "plan"

        # Pure text plan
        if len(text_segs) == 1 and not image_segs:
            return _strip_markers(text_segs[0].content), rich, "plan"

        # Multi-text plan — use response_plan for sequential delivery
        segments_out: list[dict] = [
            {"type": seg.type, "content": _strip_markers(seg.content)} for seg in plan
        ]
        rich["response_plan"] = segments_out
        combined = " ".join(_strip_markers(s.content) for s in text_segs if s.content)
        return combined, rich, "plan"

    # ── Path 2: tools ran but no plan → synthesis (LLM Call 2) ──
    if any_ran and tool_results:
        text = await _synthesize_from_results(belief, tool_results, user_message)
        if text:
            return text, rich, "synthesis"

    # ── Path 3: safe default for clarify/smalltalk/handoff ────────────
    return _SAFE_CLARIFY_ES, rich, "plan"


async def _build_photo_plan(belief, rich: dict) -> dict | None:
    """Deterministically build the photo response_plan (images + visit CTA).

    Triggered whenever get_property_images ran for a selected property — photo
    delivery must NOT depend on the engine emitting a redundant 'images' segment in
    response_plan. The engine does that inconsistently, which silently dropped the
    photos and left the user waiting ("Te muestro las fotos de ID:45" with no images).

    Returns an extended rich dict, or None if no images could be resolved (caller
    then falls through to a normal text reply). Images carry NO caption (a repeated
    caption under each photo is noise); a single CTA text segment follows the photos.
    """
    images, _title = await _resolve_images(belief)
    if not images:
        return None
    out = dict(rich)
    out["images"] = images
    out["caption"] = ""
    out["response_plan"] = [
        {"type": "images", "images": images[:_MAX_PHOTOS], "caption": ""},
        {"type": "text", "content": _PHOTO_CTA_ES},
    ]
    return out


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

async def _record_gate_history(belief, user_message: str, response_text: str) -> None:
    """Append a safety-gate turn to history + persist it (plan #24).

    Emergency/human/out-of-scope gates return BEFORE the normal step-6/8c history
    bookkeeping, so the next engine turn never saw them — e.g. after an out-of-scope
    joke the bot would re-greet as if the conversation just started. Record both sides
    and save. Fully defensive — never breaks the gate response.
    """
    try:
        from app.routers.v3.belief import save_belief_v5
        from app.core.config import get_settings
        belief.history.append(f"user: {user_message}")
        belief.history.append(f"assistant: {response_text}")
        window = get_settings().HISTORY_WINDOW
        if len(belief.history) > window:
            belief.history = belief.history[-window:]
        await save_belief_v5(belief)
    except Exception as exc:
        logger.warning("[V3] Failed to record gate turn in history: {}", str(exc))


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
        await _record_gate_history(belief, user_message, handoff_text)
        return _contract(
            handoff_text,
            ["request_human_assistance"],
            {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
             "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
            1.0, "v3::emergency", start,
        )

    # Tenant profile (cached) — timezone for the daily cap, agency name for the
    # limit message. Fetched once here; the emergency path above bypasses it.
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

    # ── Daily message cap (cost-drain protection) ────────────────────────────
    # Count every processed turn for this identity per calendar day (tenant tz).
    # Over the cap → one professional handoff message; the adapter pauses the bot
    # (request_human_assistance / limit label) until the tenant resumes it. The
    # emergency gate above is intentionally exempt so a safety message is never
    # throttled. Redis-backed with an in-process floor (survives a Redis outage).
    _daily_cap = getattr(_cfg, "USER_DAILY_MESSAGE_CAP", 40)
    if _daily_cap and _daily_cap > 0:
        try:
            from app.core.usage_limits import incr_daily_count
            _count = await incr_daily_count(session_id, _tz_name)
        except Exception:
            _count = 0
        if _count > _daily_cap:
            logger.info(
                "[V3] Daily cap hit for {} ({} > {}) — handoff + pause",
                session_id, _count, _daily_cap,
            )
            _cap_msg = _daily_cap_message(_agency)
            _emit_gate("v3::limit-daily", ["request_human_assistance"], 1.0)
            await _record_gate_history(belief, user_message, _cap_msg)
            return _contract(
                _cap_msg,
                ["request_human_assistance"],
                {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
                 "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
                1.0, "v3::limit-daily", start,
            )

    # Human handoff
    if _is_human_request(user_message):
        logger.info("[V3] Human handoff for {}: {}", session_id, user_message[:80])
        handoff_text = await _call_human_assistance("user_requested", user_message)
        _emit_gate("v3::human-handoff", ["request_human_assistance"], 1.0)
        await _record_gate_history(belief, user_message, handoff_text)
        return _contract(
            handoff_text,
            ["request_human_assistance"],
            {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
             "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
            1.0, "v3::human-handoff", start,
        )

    # ── Off-topic + abuse gate (with N-strike human escalation) ──────────────
    # Abuse is detected independently of scope (a message can mention "casa" and
    # still be abusive). Both off-topic and abusive messages increment a cumulative,
    # lifetime counter (never reset on a valid message — reset only when a tenant
    # resumes the bot). At the threshold → escalate to a human and pause; under it →
    # redirect (a firm-but-polite nudge for abuse, the scope reminder otherwise).
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
            logger.info(
                "[V3] Off-topic/abuse escalation for {} (count={}) — handoff + pause",
                session_id, belief.offtopic_abuse_count,
            )
            _emit_gate("v3::limit-abuse", ["request_human_assistance"], 1.0)
            await _record_gate_history(belief, user_message, _ABUSE_HANDOFF_ES)
            return _contract(
                _ABUSE_HANDOFF_ES,
                ["request_human_assistance"],
                {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
                 "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
                1.0, "v3::limit-abuse", start,
            )
        _redirect = _ABUSE_REDIRECT_ES if _abusive else _OUT_OF_SCOPE_RESPONSE
        _label = "v3::abuse" if _abusive else "v3::out-of-scope"
        logger.info("[V3] {} for {}: {}", _label, session_id, user_message[:80])
        _emit_gate(_label, [], 1.0)
        await _record_gate_history(belief, user_message, _redirect)
        return _contract(
            _redirect,
            [],
            {"images": [], "caption": "", "selected_property_id": belief.selected_property_id,
             "search_criteria": belief.search_criteria, "active_intents": list(belief.active_intents)},
            1.0, _label, start,
        )

    # ── Step 3: Build messages ────────────────────────────────────────────────
    from app.routers.v3 import prompts

    state_json = json.dumps(_compact_state(belief), ensure_ascii=False)
    history = _history_messages(belief)
    tenant_policy = await prompts.build_tenant_policy(tenant_id)
    messages = prompts.build_messages(
        prompts.build_system_prompt(),
        tenant_policy,
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
    # Use "user: " prefix so future turns can distinguish user vs. assistant messages.
    if not fallback_incremented:
        belief.history.append(f"user: {user_message}")
    window = settings.HISTORY_WINDOW
    if len(belief.history) > window:
        belief.history = belief.history[-window:]

    # Engine-tracking fields (capture the PRIOR intent first — plan #13 needs it to
    # detect two consecutive off-topic turns before we overwrite it).
    prev_last_intent = getattr(belief, "last_intent", None)
    belief.last_action = turn.action
    belief.last_intent = turn.intent
    belief.action_history.append(turn.action)

    # Reset-on-new-search (plan #3): a fresh search invalidates the prior selection
    # and any in-flight scheduling slots. Without this, "mostrame fotos" after a new
    # search backfills the OLD selected_property_id (step 7 backfill / _build_photo_plan),
    # and a half-finished booking leaks across — the user can see/book the wrong unit.
    requested = {tc.name for tc in (turn.tool_calls or [])}
    if "search_properties" in requested:
        # Selection + scheduling slots reset; ordinal backstop intentionally skipped
        # (an ordinal like "la primera" refers to the NEW list, resolved next turn).
        _apply_new_search_reset(belief, turn)
    # selected_property_id — engine first, then a deterministic ordinal backstop
    # ("la primera"/"el tercero" → id from the previous search) so the model's
    # inconsistent ordinal resolution can't drop the selection.
    elif turn.selected_property_id is not None:
        belief.selected_property_id = turn.selected_property_id
    else:
        _ord_id = _resolve_ordinal_to_id(user_message, belief.last_search_ids)
        if _ord_id is not None:
            belief.selected_property_id = _ord_id

    # missing_slot → awaiting
    if turn.missing_slot is not None:
        belief.awaiting = turn.missing_slot

    # Scheduling slots from missing_slot feedback
    if turn.missing_slot is None and turn.action == "book_step":
        # Scheduling completed or no slot missing — clear awaiting
        belief.awaiting = None

    # Persist concrete day/time the user gave THIS turn (plan #10) so a long booking
    # flow doesn't forget a slot once it slides out of the history window. Runs only
    # on scheduling turns; schedule_visit args are captured separately in _execute_tools.
    _persist_scheduling_slots_from_message(belief, turn, user_message)

    # Clear a stale scheduling `awaiting` after the user moved on (plan #13): if this
    # turn AND the previous one were both non-scheduling yet `awaiting` is still a
    # scheduling slot, the [ESTADO] would keep telling the LLM it's waiting for a slot
    # the user abandoned. Two consecutive off-topic turns is the signal to drop it.
    _clear_stale_scheduling_awaiting(belief, turn, prev_last_intent)

    belief.last_updated_at = time.time()

    try:
        await save_belief_v5(belief)
    except Exception as exc:
        logger.warning("[V3] save_belief_v5 failed: {}", str(exc))

    # ── Step 7: Execute tools ────────────────────────────────────────────────
    tools_used, tool_results, any_ran, booking_succeeded = await _execute_tools(turn, belief)

    # ── Step 7b: RAG safety-net for answer_knowledge (Phase 5) ───────────────
    # If engine chose answer_knowledge but didn't emit get_faq_answer in tool_calls,
    # proactively retrieve top-k knowledge chunks and inject into tool_results so
    # the synthesis step can ground the answer rather than hallucinate.
    #
    # Gate (plan #8): when the user is asking about the JUST-SHOWN search results
    # ("¿cuál es la más barata?", "¿cuál tiene más ambientes?") the model labels the
    # turn intent==search but may pick answer_knowledge with no tool. Injecting FAQ/
    # property chunks here drowns the answer in irrelevant material. Skip the net in
    # that case and let the response plan answer from ultima_busqueda in the state.
    if turn.action == "answer_knowledge" and not any_ran and not _is_about_shown_results(turn, belief):
        try:
            from app.routers.v3.knowledge.index import search_knowledge
            from app.core.config import get_settings as _get_settings
            _s = _get_settings()
            _chunks = await search_knowledge(
                tenant_id=tenant_id,
                query=user_message,
                limit=_s.KNOWLEDGE_TOP_K,
                threshold=_s.KNOWLEDGE_SIMILARITY_THRESHOLD,
            )
            if _chunks:
                snippet_text = "\n\n".join(c["text"] for c in _chunks[:3])
                tool_results.append(snippet_text)
                tools_used.append("knowledge_retrieval")
                any_ran = True
                logger.debug("[V3] RAG safety-net: {} chunks injected", len(_chunks))
        except Exception as _rag_exc:
            logger.debug("[V3] RAG safety-net failed (non-fatal): {}", str(_rag_exc))

    # Update belief with tool side-effects
    if "get_property_details" in tools_used or "get_property_images" in tools_used:
        # Update last_tool_called for state_label compat
        belief.last_tool_called = tools_used[-1]
    if "search_properties" in tools_used:
        belief.last_tool_called = "search_properties"
        # Persist the result list so the NEXT turn can resolve "la primera"/"el 3"
        # to a concrete id and answer follow-ups from the stored search.
        _persist_search_context(belief, tools_used, tool_results)

    # ── Step 7c: FSM post-engine guard ───────────────────────────────────────
    fsm_result = None
    try:
        from app.routers.v3.scheduling.fsm import resolve as fsm_resolve

        fsm_result = await fsm_resolve(
            belief,
            user_message,
            turn,
            booking_succeeded,
            tool_results,
            tenant_id,
        )
        # Re-persist belief if FSM mutated it (scheduling_loop_count, awaiting, etc.)
        try:
            await save_belief_v5(belief)
        except Exception:
            pass
    except Exception as exc:
        logger.debug("[V3] fsm.resolve error (non-fatal): {}", str(exc))

    # ── Step 8: Assemble response ─────────────────────────────────────────────
    _fsm_booking_succeeded = fsm_result.booking_succeeded if fsm_result else booking_succeeded
    _fsm_plan = (fsm_result.response_plan if (fsm_result and fsm_result.override) else None)

    response_text, rich_content, response_source = await _assemble_response(
        turn,
        belief,
        tool_results,
        any_ran,
        tenant_id,
        booking_succeeded=_fsm_booking_succeeded,
        fsm_plan=_fsm_plan,
        tools_used=tools_used,
        user_message=user_message,
    )

    # ── Step 8b: Quality guard — gated judge + one targeted regen (LLM Call 3) ─
    # Runs only on low-confidence or critical turns (book_step/handoff/knowledge);
    # most turns skip it, keeping the median call budget ≤3. Never raises.
    # EXCEPTION: a SUCCESSFUL booking confirmation is deterministic, carries the
    # real date/time/address, and must never be regenerated — an LLM rewrite could
    # silently drop those structured fields. Skip the judge entirely in that case.
    judge_score: float | None = None
    _booked_ok = (turn.action == "book_step" and _fsm_booking_succeeded)
    if not _booked_ok:
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
            # Strip any booking markers the regeneration may have copied from tool_results.
            response_text = _strip_markers(guard_result.response_text)
            judge_score = guard_result.judge_score
        except Exception as exc:
            logger.debug("[V3] guard.run_guard error (non-fatal): {}", str(exc))

    # ── Step 8c: Store assistant response in history for next turn context ────────
    # Include the bot's response so future turns can see the full conversation
    # (essential for understanding context-dependent responses like "yes/no" to questions).
    try:
        belief.history.append(f"assistant: {response_text}")
        window = settings.HISTORY_WINDOW
        if len(belief.history) > window:
            belief.history = belief.history[-window:]
        await save_belief_v5(belief)
    except Exception as exc:
        # Promoted from debug (plan #15): losing the assistant turn means the next
        # turn can't see what the bot just said — a real context hole, not noise.
        logger.warning("[V3] Failed to append assistant response to history: {}", str(exc))

    # ── Step 9: Metrics + return ─────────────────────────────────────────────
    router_label = f"v3::{turn.action}"
    # Scheduling-loop escalation: the FSM gave up coordinating the visit (T-6) and
    # routed to a human. Re-label as a handoff and surface request_human_assistance so
    # the adapter pauses the bot + notifies the agency — previously this message was
    # sent to the user but the bot kept answering (a real escalation gap).
    try:
        from app.routers.v3.scheduling.fsm import SchedulingState as _SchedState
        if fsm_result and getattr(fsm_result, "next_state", None) == _SchedState.HANDOFF:
            router_label = "v3::human-handoff"
            if "request_human_assistance" not in tools_used:
                tools_used.append("request_human_assistance")
    except Exception:
        pass
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
            judge_score=judge_score,
        )
    except Exception:
        pass

    logger.debug(
        "[V3] action={} intent={} tools={} latency={:.0f}ms conf={:.2f} src={} judge={}",
        turn.action, turn.intent, tools_used, latency_ms, turn.confidence, extraction_source, judge_score,
    )

    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "confidence": turn.confidence,
        "router_label": router_label,
        "latency_ms": latency_ms,
    }
