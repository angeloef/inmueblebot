"""Conversation manager — handles topic switching and state save/restore (Phase 8).

When a user interrupts a flow (e.g., asks about prices mid-scheduling),
the conversation manager saves the current specialist state and switches topics.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationSnapshot:
    """Saved state when a conversation is interrupted."""
    active_specialist: str = ""
    specialist_state: dict = field(default_factory=dict)
    turn_in_specialist: int = 0


# In-memory store: session_id → snapshot
_snapshots: dict[str, ConversationSnapshot] = {}


def save_specialist_state(
    session_id: str,
    specialist_name: str,
    state: dict | None = None,
) -> None:
    """Save the current specialist context before switching topics."""
    _snapshots[session_id] = ConversationSnapshot(
        active_specialist=specialist_name,
        specialist_state=state or {},
        turn_in_specialist=0,
    )


def get_saved_state(session_id: str) -> Optional[ConversationSnapshot]:
    """Get the saved state for a session, if any."""
    return _snapshots.get(session_id)


def clear_saved_state(session_id: str) -> None:
    """Clear saved state when the flow is complete."""
    _snapshots.pop(session_id, None)


def detect_topic_switch(
    current_specialist: str,
    new_intent: str,
) -> bool:
    """Detect if the user is switching topics mid-flow."""
    if current_specialist == new_intent:
        return False

    # Some transitions are natural (don't count as interruptions)
    NATURAL_TRANSITIONS = {
        ("search", "scheduling"),
        ("search", "knowledge"),
        ("search", "negotiator"),
        ("scheduling", "knowledge"),
        ("rapport", "search"),
        ("rapport", "knowledge"),
        ("rapport", "scheduling"),
    }

    return (current_specialist, new_intent) not in NATURAL_TRANSITIONS


def build_interruption_prompt(
    previous_specialist: str,
    new_intent: str,
) -> str:
    """Build a prompt acknowledging the topic switch."""
    specialist_descriptions = {
        "search": "búsqueda de propiedades",
        "scheduling": "agendamiento de visita",
        "knowledge": "información general",
        "negotiator": "negociación de precios",
        "rapport": "conversación",
    }

    prev_desc = specialist_descriptions.get(previous_specialist, previous_specialist)
    new_desc = specialist_descriptions.get(new_intent, new_intent)

    return (
        f"El usuario cambió de tema. Estábamos en {prev_desc} "
        f"y ahora pregunta sobre {new_desc}. Atendé la nueva consulta.\n\n"
        f"Cuando termines, ofrecé volver al tema anterior: "
        f"'¿Seguimos con {prev_desc}?'"
    )
