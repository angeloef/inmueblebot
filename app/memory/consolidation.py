"""MemoryConsolidator — summarize session → update memory → prune (Phase 7).

Runs after each session to:
1. Generate a session summary
2. Save to episodic memory
3. Update user persona
4. Update zone stats
5. Prune old data
"""

from app.memory.episodic import save_episode
from app.memory.user_model import update_persona
from app.memory.semantic import increment_zone_search
from app.memory.procedural import get_most_used_skill
from app.core.belief_state import ConversationBeliefState
from app.core.identity import get_identity_key


async def consolidate_session(
    belief: ConversationBeliefState,
    phone: str = "",
) -> dict:
    """Run the full memory consolidation pipeline after a session.

    Args:
        belief: Final belief state from the session.
        phone: User's phone number for cross-session tracking.

    Returns:
        dict with consolidation results.
    """
    results = {
        "episode_saved": False,
        "persona_updated": False,
        "zone_updated": False,
        "summary": "",
    }

    session_id = belief.session_id
    canonical_id = get_identity_key() or phone

    # 1. Generate summary
    summary = _summarize_session(belief)
    results["summary"] = summary

    # 2. Save episode (if phone provided)
    if canonical_id:
        await save_episode(
            phone=canonical_id,
            session_id=session_id,
            summary=summary,
            turn_count=belief.turn_count,
            search_criteria=belief.search_criteria if belief.search_criteria else None,
            properties_viewed=[belief.selected_property_id] if belief.selected_property_id else [],
            last_tool=belief.last_tool_called,
            intent_outcome=_classify_outcome(belief),
        )
        results["episode_saved"] = True

        # 3. Update persona
        updates = {"session_count": 1}
        if belief.operation:
            updates["operation"] = belief.operation
        if belief.zone:
            updates["zone"] = belief.zone
        if belief.property_type:
            updates["property_type"] = belief.property_type
        if belief.budget_max:
            updates["budget_max"] = belief.budget_max
        if belief.selected_property_id:
            updates["properties_viewed"] = [belief.selected_property_id]

        await update_persona(canonical_id, updates)
        results["persona_updated"] = True

        # 4. Update zone stats
        if belief.zone:
            await increment_zone_search(belief.zone)
            results["zone_updated"] = True

    return results


def _summarize_session(belief: ConversationBeliefState) -> str:
    """Generate a compact summary of the session."""
    parts = [f"Sesión de {belief.turn_count} turnos"]

    if belief.operation:
        parts.append(f"buscando {belief.operation}")

    if belief.property_type:
        parts.append(belief.property_type)

    if belief.zone:
        parts.append(f"en {belief.zone}")

    if belief.budget_max:
        parts.append(f"hasta ${belief.budget_max:,.0f}")

    if belief.selected_property_id:
        parts.append(f"— vio propiedad #{belief.selected_property_id}")

    if belief.last_tool_called:
        parts.append(f"| última acción: {belief.last_tool_called}")

    return " ".join(parts)


def _classify_outcome(belief: ConversationBeliefState) -> str:
    """Classify the session outcome based on state."""
    if belief.selected_property_id and "scheduling" in belief.active_intents:
        return "scheduled_visit"
    if belief.selected_property_id:
        return "viewed_property"
    if belief.last_search_count > 0:
        return "searched_with_results"
    if belief.last_tool_called == "search_properties":
        return "searched_no_results"
    if "searching" in belief.active_intents:
        return "started_search"
    return "browsing"
