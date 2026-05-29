"""Context aggregator — builds enriched LLM system prompt from belief state.

Injects accumulated criteria, active intents, and conversation history
into the LLM context for multi-turn awareness.
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


def build_context_prompt(belief: ConversationBeliefState) -> str:
    """Build an additional context block to prepend to the LLM system prompt.

    Gives the LLM awareness of what's been discussed across turns.
    """
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

    # Pending offer (for confirmation follow-through)
    if belief.pending_offer:
        parts.append(f"OFERTA PENDIENTE: La última vez le ofreciste al usuario: {belief.pending_offer}. Si el usuario dice 'si' o confirma, ejecutá esa acción AHORA.")

    # Scheduling progress (action-oriented)
    if "scheduling" in (belief.active_intents or set()) or belief.scheduling_name or belief.scheduling_phone or belief.scheduling_day or belief.scheduling_time:
        fields = []
        if belief.scheduling_name:
            fields.append(f"nombre={belief.scheduling_name}")
        if belief.scheduling_phone:
            fields.append(f"teléfono={belief.scheduling_phone}")
        if belief.scheduling_day:
            fields.append(f"día={belief.scheduling_day}")
        if belief.scheduling_time:
            fields.append(f"horario={belief.scheduling_time}")
        
        missing_sched = []
        if not belief.scheduling_name:
            missing_sched.append("nombre")
        if not belief.scheduling_phone:
            missing_sched.append("teléfono")
        if not belief.scheduling_day:
            missing_sched.append("día")
        if not belief.scheduling_time:
            missing_sched.append("horario")
        
        if fields:
            parts.append(f"Agendamiento en curso — datos recolectados: {', '.join(fields)}")
        
        if missing_sched:
            if len(missing_sched) == 1:
                parts.append(f"ACCIÓN: Preguntale al usuario su {missing_sched[0]}.")
            else:
                parts.append(f"ACCIÓN: Preguntale al usuario: {', '.join(missing_sched)}.")
        else:
            parts.append(
                f"ACCIÓN: Ya tenés todos los datos (nombre, teléfono, día, horario). "
                f"LLAMÁ a schedule_visit AHORA con property_id={belief.selected_property_id or 'el que corresponda'}, "
                f"nombre='{belief.scheduling_name}', telefono='{belief.scheduling_phone}', "
                f"dia='{belief.scheduling_day}', horario='{belief.scheduling_time}'."
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
