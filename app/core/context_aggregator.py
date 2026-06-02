"""Context aggregator — builds enriched LLM system prompt from belief state.

Injects accumulated criteria, active intents, and conversation history
into the LLM context for multi-turn awareness.

Two engines:
- Directive engine (USE_DIRECTIVE_ENGINE=True, default): state-facts + single-directive.
- Legacy engine (USE_DIRECTIVE_ENGINE=False): original imperative-stacking approach.
"""

from app.core.belief_state import ConversationBeliefState


def detect_clarification_loop(belief: ConversationBeliefState) -> str | None:
    """Detect if we're stuck in a clarification loop (re-asking same questions).
    Returns a forceful instruction string if a loop is detected, None otherwise."""
    if belief.turn_count < 3:
        return None
    # Check last 3+ user messages for oscillation pattern
    if len(belief.history) >= 3:
        recent = [m.lower().strip() for m in belief.history[-3:]]
        ops = {'alquilar', 'alquiler', 'venta', 'comprar', 'compra'}
        types = {'departamento', 'depto', 'depa', 'casa', 'ph', 'terreno', 'monoambiente'}
        clarifying = {'alquilar o comprar', 'alquiler o venta', 'departamento o casa', 'alquilar o compra',
                      'alquilo o compro', 'buscas para alquilar', 'alquilar o comprar?'}

        # Pattern 1: Oscillation (op → type → op → type ...)
        is_oscillating = len(recent) >= 3
        for i, msg in enumerate(recent):
            if i % 2 == 0:
                if not any(op in msg for op in ops):
                    is_oscillating = False
                    break
            else:
                if not any(t in msg for t in types):
                    is_oscillating = False
                    break

        # Pattern 2: Repetition — user keeps sending single-word clarifications
        is_repeating = all(len(msg.split()) <= 2 for msg in recent) and len(set(recent)) <= 2

        # Pattern 3: Repeated clarification questions in the last prompt
        is_clarify_loop = any(kw in (''.join(recent[-2:]) if len(recent) >= 2 else '') for kw in clarifying)

        if is_oscillating or is_repeating or is_clarify_loop:
            # Build what we know
            parts = []
            if belief.operation:
                parts.append(f"operación={belief.operation}")
            if belief.property_type:
                parts.append(f"tipo={belief.property_type}")
            if belief.zone:
                parts.append(f"zona={belief.zone}")
            if belief.budget_max:
                parts.append(f"presupuesto=${belief.budget_max:,.0f}")

            return (
                "⚠️ ALERTA DE BUCLE: Ya le preguntaste al usuario lo mismo 3+ veces y no avanza. "
                f"Ya sabés: {', '.join(parts)}. "
                "EJECUTÁ search_properties AHORA con lo que tengas. NO preguntes más. "
                "Si encontrás pocos resultados, el usuario puede refinar después."
            )
    return None


def _user_confirmed(belief: ConversationBeliefState) -> bool:
    """Heuristic: did the last user message look like a confirmation?"""
    if not belief.history:
        return False
    last = belief.history[-1].lower()
    confirm_words = ["sí", "si", "dale", "ok", "perfecto", "genial", "me sirve",
                     "mostrame", "confirmo", "bueno", "listo", "adelante", "joya"]
    return any(w in last for w in confirm_words)


def _next_action_directive(belief: ConversationBeliefState) -> str:
    """Return a single directive for this turn. First match wins."""

    # Priority 1: pending confirmation to execute
    if belief.pending_offer and _user_confirmed(belief):
        return f"ACCIÓN: El usuario confirmó. Ejecutá la acción pendiente: {belief.pending_offer}"

    # Priority 2: property resolved by description, need details
    if (hasattr(belief, 'resolved_by_description') and
            'resolved_by_description' in (belief.active_intents or set()) and
            belief.selected_property_id):
        return f"ACCIÓN: Llamá get_property_details con id={belief.selected_property_id}"

    # Priority 3: scheduling — all data present, book now
    if 'scheduling' in (belief.active_intents or set()):
        if belief.scheduling_day and belief.scheduling_time and belief.scheduling_name:
            return "ACCIÓN: Tenés día, hora y nombre. Llamá schedule_visit ahora."
        elif belief.scheduling_day and not belief.scheduling_time:
            return "ACCIÓN: Falta la hora. Preguntá solo por la hora (no preguntes más nada)."
        elif belief.scheduling_time and not belief.scheduling_day:
            return "ACCIÓN: Falta el día. Preguntá solo por el día."
        elif not belief.scheduling_name:
            return "ACCIÓN: Falta el nombre para la cita. Preguntá solo por el nombre."

    # Priority 3.5: user already selected a specific property from results
    if (belief.selected_property_id
            and 'scheduling' not in (belief.active_intents or set())):
        intents = belief.active_intents or set()
        if 'photos' in intents:
            return (
                f"ACCIÓN: Llamá get_property_images con property_id={belief.selected_property_id}. "
                "El usuario ya eligió esta propiedad, ejecutá directamente."
            )
        return (
            f"ACCIÓN: Llamá get_property_details con property_id={belief.selected_property_id}. "
            "El usuario ya eligió esta propiedad, ejecutá directamente."
        )

    # Priority 4: criteria sufficient to search
    if belief.operation and belief.property_type:
        return "ACCIÓN: Tenés operación y tipo. Buscá propiedades ahora con los filtros conocidos."

    # Priority 5: need first criterion
    if not belief.operation:
        return "ACCIÓN: Preguntá si busca alquilar o comprar (una sola pregunta)."
    if not belief.property_type:
        return "ACCIÓN: Preguntá qué tipo de propiedad busca (una sola pregunta)."

    return ""


def build_context_prompt(belief: ConversationBeliefState) -> str:
    """Build an additional context block to prepend to the LLM system prompt."""
    from app.core.config import get_settings
    settings = get_settings()

    # Feature flag: fall back to legacy engine if directive engine is disabled
    if not getattr(settings, 'USE_DIRECTIVE_ENGINE', True):
        return _legacy_build_context_prompt(belief)

    if belief.is_first_turn:
        return ""

    # ── State facts block ─────────────────────────────────────
    lines = ["[ESTADO ACTUAL]"]
    lines.append(f"- Operación: {belief.operation or 'no definida'}")
    lines.append(f"- Tipo: {belief.property_type or 'no definido'}")
    lines.append(f"- Zona: {belief.zone or 'no definida'}")
    lines.append(f"- Presupuesto: {'${:,.0f}'.format(belief.budget_max) if belief.budget_max else 'no definido'}")
    lines.append(f"- Dormitorios mín: {belief.bedrooms_min if belief.bedrooms_min is not None else 'no definido'}")
    lines.append(f"- Propiedad seleccionada: {belief.selected_property_id or 'ninguna'}")
    lines.append(f"- Última herramienta: {belief.last_tool_called or 'ninguna'}")
    lines.append(f"- Turno: {belief.turn_count}")

    # ── Recent history ─────────────────────────────────────────
    if len(belief.history) > 1:
        lines.append("")
        lines.append("[HISTORIAL RECIENTE]")
        recent = belief.history[-settings.HISTORY_WINDOW:]
        for msg in recent:
            lines.append(f"Usuario: {msg[:120]}")

    # ── Search history ─────────────────────────────────────────
    if belief.search_history:
        lines.append("")
        lines.append("[BÚSQUEDAS PREVIAS]")
        for idx, entry in enumerate(belief.search_history):
            criteria_parts = []
            c = entry.get("criteria", {})
            if c.get("operation"):
                criteria_parts.append(f"op={c['operation']}")
            if c.get("tipo"):
                criteria_parts.append(f"tipo={c['tipo']}")
            if c.get("zona"):
                criteria_parts.append(f"zona={c['zona']}")
            criteria_str = " ".join(criteria_parts) if criteria_parts else "sin filtros"
            lines.append(f"Búsqueda {idx + 1}: {criteria_str} → {entry.get('count', 0)} resultados")

    # Last search context (for resolving descriptive references)
    if belief.last_search_context:
        lines.append(f"Resultados último listado (usá estos IDs): {belief.last_search_context}")

    # ── Directive block ────────────────────────────────────────
    directive = _next_action_directive(belief)

    # Append loop alert to directive if detected
    loop_alert = detect_clarification_loop(belief)
    if loop_alert:
        directive = (directive + "\n" if directive else "") + "ALERTA: El usuario preguntó lo mismo varias veces. Buscá con lo que tenés, no pidas más datos."

    if directive:
        lines.append("")
        lines.append("[DIRECTIVA PARA ESTE TURNO]")
        lines.append(directive)

    return "\n".join(lines) + "\n"


def _legacy_build_context_prompt(belief: ConversationBeliefState) -> str:
    """Legacy imperative-stacking context builder (USE_DIRECTIVE_ENGINE=False)."""
    if belief.is_first_turn:
        return ""

    parts = ["[CONTEXTO DE LA CONVERSACIÓN]"]

    # Loop detection — force-search if oscillating
    loop_alert = detect_clarification_loop(belief)
    if loop_alert:
        parts = [loop_alert] + parts

    # ⚠️ Authoritative preference lock: when operation+type are set, forbid re-asking
    if belief.operation and belief.property_type:
        parts.append(
            f"⚠️ PREFERENCIAS CONFIRMADAS: El usuario ya estableció que busca "
            f"{belief.operation.upper()} de {belief.property_type.upper()}"
            + (f" en {belief.zone}" if belief.zone else "")
            + (f" hasta ${belief.budget_max:,.0f}" if belief.budget_max else "")
            + ". NO preguntes de nuevo por operación ni tipo de propiedad — "
            "ya están definidos. Si el mensaje del usuario es corto o ambiguo, "
            "interpretalo como confirmación y procedé a buscar con estos criterios."
        )

    # Cross-criteria guard
    if belief.operation or belief.property_type:
        guard_parts = []
        if belief.operation:
            guard_parts.append(f"{belief.operation}")
        if belief.property_type:
            guard_parts.append(f"de {belief.property_type}")
        if guard_parts:
            parts.append(
                f"⚠️ El usuario busca {' '.join(guard_parts)}. "
                "No recomiendes propiedades fuera de estos criterios sin que el usuario los cambie explícitamente."
            )

    # Search criteria accumulated
    if belief.search_criteria:
        criteria_str = ", ".join(
            f"{k}: {v}" for k, v in belief.search_criteria.items()
        )
        parts.append(f"Criterios de búsqueda acumulados: {criteria_str}")
        parts.append(f"Criterios completados: {belief.search_criteria_count}/4")

    # Active intents
    if belief.active_intents:
        intents_str = ", ".join(sorted(belief.active_intents))
        parts.append(f"Intenciones activas: {intents_str}")

    # Selected property
    if belief.selected_property_id:
        parts.append(
            f"El usuario seleccionó la propiedad ID {belief.selected_property_id}"
        )

    # Forceful override when property was resolved programmatically
    if "resolved_by_description" in (belief.active_intents or set()) and belief.selected_property_id:
        parts.append(
            f"⚠️ PROPIEDAD IDENTIFICADA AUTOMÁTICAMENTE: El sistema determinó que el usuario "
            f"se refiere a la propiedad ID {belief.selected_property_id}. "
            f"USÁ get_property_details({belief.selected_property_id}) DIRECTAMENTE. "
            f"NO llames a search_properties — el ID ya fue resuelto. "
            f"Mostrá los detalles sin pedir confirmación."
        )

    # Known property data (for answering cost/service questions without re-fetching)
    if belief.selected_property_id and belief.last_tool_called == "get_property_images":
        parts.append(
            "⚠️ NO OFREZCAS FOTOS: Ya le enviaste las fotos de esta propiedad "
            "en el turno anterior. NO digas 'si querés te paso las fotos' ni "
            "ofrezcas mostrarlas de nuevo — el usuario ya las tiene."
        )
    if belief.selected_property_id and belief.last_tool_called == "get_property_details":
        if belief.last_property_data:
            parts.append(
                f"DATOS DE LA PROPIEDAD {belief.selected_property_id}: "
                f"{belief.last_property_data}. "
                "Si el usuario pregunta por costos, servicios, dirección o características, "
                "usá ESTOS datos. NO llames a get_faq_answer para preguntas sobre esta propiedad específica."
            )
        if belief.last_shown_detail_id == belief.selected_property_id:
            parts.append(
                "⚠️ NO REPITAS: Ya le mostraste los detalles completos de esta propiedad. "
                "NO llames a get_property_details de nuevo. "
                "Si el usuario dice 'dale', 'me gusta', 'me interesa', 'ok' o confirma, "
                "preguntale si quiere coordinar una visita, ver fotos, o pasar al siguiente paso. "
                "JAMÁS repitas los detalles que ya mostraste."
            )

    # Cost question override
    if belief.selected_property_id and belief.last_property_data:
        cost_keywords = ["cuanto", "cuánto", "precio", "cuesta", "sale", "entrar", "ingresar"]
        msg_lower = (belief.history[-1] if belief.history else "").lower()
        if any(kw in msg_lower for kw in cost_keywords):
            parts.append(
                f"⚠️ PREGUNTA DE COSTOS: El usuario preguntó sobre precios de la propiedad {belief.selected_property_id}. "
                f"Respondé con los DATOS DE LA PROPIEDAD que ya tenés. NO llames a get_property_details ni search_properties. "
                f"Si necesitás info que no tenés (ej: si los servicios están incluidos), usá get_faq_answer."
            )

    # Last action
    if belief.last_tool_called:
        parts.append(f"Última acción: {belief.last_tool_called}")

    # Last search context (for resolving descriptive references)
    if belief.last_search_context:
        parts.append(f"Resultados de la última búsqueda (usá estos IDs para resolver referencias como 'el primero', 'el monoambiente'): {belief.last_search_context}")

    # ── Search history (for cross-turn disambiguation) ──────────
    if belief.search_history:
        history_parts = ["Búsquedas recientes del usuario:"]
        for idx, entry in enumerate(belief.search_history):
            criteria_str = ", ".join(f"{k}: {v}" for k, v in entry.get("criteria", {}).items())
            history_parts.append(f"[BÚSQUEDA {idx+1}: {criteria_str}]")
            ctx_lines = entry.get("context", "").split(" | ")
            for ctx_line in ctx_lines[:3]:  # Show at most 3 per search
                history_parts.append(f"  {ctx_line.strip()}")
            history_parts.append(f"  ({entry.get('count', 0)} resultados)")

        # Only show disambiguation hint when no property is selected AND
        # the current message likely refers to past results
        if not belief.selected_property_id and "resolved_by_description" not in (belief.active_intents or set()):
            history_parts.append(
                "⚠️ El usuario puede estar refiriéndose a propiedades de búsquedas anteriores. "
                "Si menciona una zona, tipo o característica, buscá en el historial de búsquedas arriba."
            )

        parts.append("\n".join(history_parts))

    # Pending offer (for confirmation follow-through)
    if belief.pending_offer:
        parts.append(
            f"⚠️ OFERTA PENDIENTE: Le ofreciste al usuario: {belief.pending_offer}. "
            "Si el usuario dice 'sí', 'dale', 'mostrame', 'si mostrame' o cualquier confirmación, "
            "ejecutá esa acción AHORA sin preguntar nada más. NO repitas la oferta."
        )

    # Scheduling progress (action-oriented)
    if "scheduling" in (belief.active_intents or set()) or belief.scheduling_name or belief.scheduling_phone or belief.scheduling_day or belief.scheduling_time:
        # NOTE (Meta identity migration): el teléfono NO se pide ni se requiere —
        # la identidad/contacto sale del WhatsApp del usuario. Los bloqueadores son
        # día + horario (lo necesario para parsear la fecha). El nombre lo toma el
        # LLM de la conversación y lo valida schedule_visit.
        fields = []
        if belief.scheduling_name:
            fields.append(f"nombre={belief.scheduling_name}")
        if belief.scheduling_day:
            fields.append(f"día={belief.scheduling_day}")
        if belief.scheduling_time:
            fields.append(f"horario={belief.scheduling_time}")

        missing_sched = []
        if not belief.scheduling_day:
            missing_sched.append("día")
        if not belief.scheduling_time:
            missing_sched.append("horario")

        if fields:
            parts.append(f"Agendamiento en curso — datos recolectados: {', '.join(fields)}")

        if missing_sched:
            parts.append(
                f"ACCIÓN: Pedile al usuario: {', '.join(missing_sched)}. "
                f"NUNCA pidas el teléfono (ya lo tenemos del WhatsApp)."
            )
        else:
            parts.append(
                f"ACCIÓN: Ya tenés día y horario. LLAMÁ a schedule_visit AHORA con "
                f"property_id={belief.selected_property_id or 'el que corresponda'}, "
                f"nombre='{belief.scheduling_name or 'el nombre que dio el usuario en la conversación'}', "
                f"dia='{belief.scheduling_day}', horario='{belief.scheduling_time}'. "
                f"NUNCA pidas el teléfono. NO confirmes la cita en texto sin antes llamar a schedule_visit."
            )

    # History summary
    if len(belief.history) > 1:
        recent = belief.history[-3:]
        history_str = " | ".join(f'"{m[:50]}"' for m in recent)
        parts.append(f"Últimos mensajes: {history_str}")

    # Missing criteria hints
    # Only nag about missing criteria when NOT just after a search — the LLM already has results
    if belief.last_tool_called != "search_properties":
        missing = _get_missing_criteria(belief)
        if missing:
            if belief.operation and belief.property_type:
                parts.append(f"Ya tenés operación ({belief.operation}) y tipo ({belief.property_type}). Buscá con eso.")
            else:
                parts.append(f"Falta definir: {', '.join(missing)}")

    return "\n".join(parts) + "\n"


def _get_missing_criteria(belief: ConversationBeliefState) -> list[str]:
    """Return list of missing search criteria names."""
    missing = []
    if belief.operation is None:
        missing.append("operación (alquiler/venta)")
    if belief.property_type is None:
        missing.append("tipo de propiedad")
    if belief.zone is None:
        missing.append("zona")
    if belief.budget_max is None:
        missing.append("presupuesto máximo")
    return missing
