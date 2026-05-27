"""Guard functions — 12 boolean predicates on ConversationBeliefState.

Replace 168 hardcoded state transitions with composable guard checks.
"""

from app.core.belief_state import ConversationBeliefState


# ── Action Guards ─────────────────────────────────────────────


def can_greet(belief: ConversationBeliefState) -> bool:
    """Greeting is always valid."""
    return True


def can_search(belief: ConversationBeliefState) -> bool:
    """User has enough criteria OR explicitly asking to search."""
    return (
        belief.search_criteria_count >= 4
        or "searching" in belief.active_intents
    )


def can_search_with_partial(belief: ConversationBeliefState) -> bool:
    """User has at least 2 criteria — enough for a broad search."""
    return belief.search_criteria_count >= 2 or "searching" in belief.active_intents


def can_view_details(belief: ConversationBeliefState) -> bool:
    """A property is selected, can show details."""
    return belief.selected_property_id is not None


def can_view_photos(belief: ConversationBeliefState) -> bool:
    """Property selected AND user wants visual info."""
    return belief.selected_property_id is not None and any(
        i in belief.active_intents for i in ("viewing", "photos", "detalles")
    )


def can_schedule(belief: ConversationBeliefState) -> bool:
    """Property selected AND scheduling intent expressed."""
    return (
        belief.selected_property_id is not None
        and "scheduling" in belief.active_intents
    )


def can_ask_faq(belief: ConversationBeliefState) -> bool:
    """FAQ can be asked at any time."""
    return True


def can_confirm(belief: ConversationBeliefState) -> bool:
    """Confirmation valid when there's a pending action to confirm."""
    return belief.last_tool_called is not None or belief.turn_count > 0


# ── Clarification Guards ─────────────────────────────────────


def needs_clarify_operation(belief: ConversationBeliefState) -> bool:
    """Search intent but no operation (alquiler/venta) specified."""
    return "searching" in belief.active_intents and belief.operation is None


def needs_clarify_type(belief: ConversationBeliefState) -> bool:
    """Search intent but no property type specified."""
    return (
        "searching" in belief.active_intents
        and belief.property_type is None
        and belief.search_criteria_count >= 1
    )


def needs_clarify_zone(belief: ConversationBeliefState) -> bool:
    """Search intent but no zone specified, and we have enough other criteria."""
    return (
        "searching" in belief.active_intents
        and belief.zone is None
        and belief.search_criteria_count >= 3
    )


def needs_clarify_budget(belief: ConversationBeliefState) -> bool:
    """Search intent but no budget, and we're about to search."""
    return (
        "searching" in belief.active_intents
        and belief.budget_max is None
        and belief.search_criteria_count >= 2
    )


def should_handoff(belief: ConversationBeliefState) -> bool:
    """Multiple turns without progress → suggest human handoff."""
    return (
        belief.turn_count >= 6
        and belief.search_criteria_count == 0
        and not belief.selected_property_id
        and len(belief.active_intents) == 0
    )


# ── All guards registry ──────────────────────────────────────

ALL_GUARDS = {
    "can_greet": can_greet,
    "can_search": can_search,
    "can_search_with_partial": can_search_with_partial,
    "can_view_details": can_view_details,
    "can_view_photos": can_view_photos,
    "can_schedule": can_schedule,
    "can_ask_faq": can_ask_faq,
    "can_confirm": can_confirm,
    "needs_clarify_operation": needs_clarify_operation,
    "needs_clarify_type": needs_clarify_type,
    "needs_clarify_zone": needs_clarify_zone,
    "needs_clarify_budget": needs_clarify_budget,
    "should_handoff": should_handoff,
}
