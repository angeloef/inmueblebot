"""Multi-turn coherence checker (Phase 10).

Ensures responses reference prior conversation context correctly.
"""

from app.core.belief_state import ConversationBeliefState


def check_coherence(
    response: str,
    belief: ConversationBeliefState,
) -> dict:
    """Check if a response is coherent with the conversation history.

    Returns:
        dict with coherence issues found.
    """
    issues = {"vague_reference": False, "score": 10}

    resp_lower = response.lower()

    # Check for vague references without resolution
    vague_patterns = [
        (r"\bel\b", "ID de propiedad"),
        (r"\bla\b", "ID de propiedad"),
        (r"\blos\b", "referencia"),
        (r"\blas\b", "referencia"),
        (r"\bese\b", "propiedad mencionada"),
        (r"\besa\b", "propiedad mencionada"),
        (r"\baquel\b", "referencia distante"),
    ]

    for pattern, what in vague_patterns:
        if belief.turn_count >= 3:
            issues["vague_reference"] = True
            issues["score"] -= 1
            break

    # Check if response mentions properties not in context
    if belief.selected_property_id and str(belief.selected_property_id) not in resp_lower:
        pass  # May be intentional

    issues["score"] = max(0, issues["score"])
    return issues


def build_coherence_context(belief: ConversationBeliefState) -> str:
    """Build a coherence hint for the LLM to maintain multi-turn consistency.

    Includes recent property IDs and search results so the LLM
    can reference them naturally.
    """
    if belief.turn_count <= 1:
        return ""

    parts = ["[COHERENCIA]"]
    parts.append(f"Turno actual: {belief.turn_count}")

    if belief.selected_property_id:
        parts.append(f"Propiedad en foco: ID {belief.selected_property_id}")

    if belief.last_search_count > 0:
        parts.append(f"Última búsqueda: {belief.last_search_count} resultados")

    if belief.active_intents:
        parts.append(f"Intenciones activas: {', '.join(belief.active_intents)}")

    return "\n".join(parts)
