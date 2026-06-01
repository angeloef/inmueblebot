"""Conversation manager — handles topic switching and state save/restore (Phase 8).

When a user interrupts a flow (e.g., asks about prices mid-scheduling),
the conversation manager saves the current specialist state and switches topics.

Snapshots are persisted to Redis (L2) with in-memory dict as L1 cache.
Falls back to in-memory-only if Redis is unavailable.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.core.config import get_settings


@dataclass
class ConversationSnapshot:
    """Saved state when a conversation is interrupted."""
    active_specialist: str = ""
    specialist_state: dict = field(default_factory=dict)
    turn_in_specialist: int = 0


# In-memory L1 cache: session_id → snapshot
_snapshots: dict[str, ConversationSnapshot] = {}


async def save_specialist_state(
    session_id: str,
    specialist_name: str,
    state: dict | None = None,
) -> None:
    """Save the current specialist context before switching topics."""
    snapshot = ConversationSnapshot(
        active_specialist=specialist_name,
        specialist_state=state or {},
        turn_in_specialist=0,
    )
    # L1: in-memory
    _snapshots[session_id] = snapshot

    # L2: Redis
    try:
        redis = await _get_redis()
        if redis:
            settings = get_settings()
            key = f"specialist:{session_id}"
            data = json.dumps({
                "active_specialist": snapshot.active_specialist,
                "specialist_state": snapshot.specialist_state,
                "turn_in_specialist": snapshot.turn_in_specialist,
            })
            await redis.set(key, data, ex=settings.WORKING_MEMORY_TTL)
            await redis.aclose()
    except Exception:
        pass  # Redis failure is non-fatal — in-memory fallback is sufficient


async def get_saved_state(session_id: str) -> Optional[ConversationSnapshot]:
    """Get the saved state for a session, if any.

    Checks L1 (in-memory) first, then L2 (Redis).
    """
    # L1: in-memory
    if session_id in _snapshots:
        return _snapshots[session_id]

    # L2: Redis
    try:
        redis = await _get_redis()
        if redis:
            key = f"specialist:{session_id}"
            data = await redis.get(key)
            await redis.aclose()
            if data:
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                d = json.loads(data)
                snapshot = ConversationSnapshot(
                    active_specialist=d.get("active_specialist", ""),
                    specialist_state=d.get("specialist_state", {}),
                    turn_in_specialist=d.get("turn_in_specialist", 0),
                )
                # Warm L1 cache
                _snapshots[session_id] = snapshot
                return snapshot
    except Exception:
        pass

    return None


async def clear_saved_state(session_id: str) -> None:
    """Clear saved state when the flow is complete."""
    # L1
    _snapshots.pop(session_id, None)

    # L2: Redis
    try:
        redis = await _get_redis()
        if redis:
            await redis.delete(f"specialist:{session_id}")
            await redis.aclose()
    except Exception:
        pass


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


async def _get_redis():
    """Get Redis connection via MemoryManager connection pool."""
    try:
        from app.core.memory import MemoryManager
        mm = MemoryManager()
        r = await mm._get_redis_with_retry()
        return r
    except Exception:
        return None
