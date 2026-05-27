"""WorkingMemory — current conversation state with Redis persistence (Phase 7).

Wraps ConversationBeliefState with Redis caching (TTL: 1 hour).
Falls back to in-memory dict when Redis is unavailable.
"""

import json
from typing import Optional

from app.core.belief_state import (
    ConversationBeliefState,
    _session_store as _fallback_store,
)
from app.core.config import get_settings
settings = get_settings()


async def save_working_memory(belief: ConversationBeliefState) -> None:
    """Persist working memory to Redis with 1-hour TTL."""
    key = f"working:{belief.session_id}"
    data = _serialize_belief(belief)

    redis = await _get_redis()
    if redis:
        await redis.set(key, data, ex=3600)
        await redis.aclose()
    else:
        # Fallback to in-memory
        from app.core.belief_state import save_belief
        save_belief(belief)


async def load_working_memory(session_id: str) -> Optional[ConversationBeliefState]:
    """Load working memory from Redis or fallback store."""
    key = f"working:{session_id}"

    redis = await _get_redis()
    if redis:
        data = await redis.get(key)
        await redis.aclose()
        if data:
            return _deserialize_belief(data, session_id)

    # Fallback: in-memory store
    from app.core.belief_state import get_belief
    belief = get_belief(session_id)
    return belief if belief.turn_count > 0 else None


async def clear_working_memory(session_id: str) -> None:
    """Remove working memory for a session."""
    key = f"working:{session_id}"

    redis = await _get_redis()
    if redis:
        await redis.delete(key)
        await redis.aclose()


def _serialize_belief(belief: ConversationBeliefState) -> str:
    """Serialize belief state to JSON for Redis storage."""
    return json.dumps({
        "session_id": belief.session_id,
        "operation": belief.operation,
        "property_type": belief.property_type,
        "zone": belief.zone,
        "budget_max": belief.budget_max,
        "bedrooms_min": belief.bedrooms_min,
        "selected_property_id": belief.selected_property_id,
        "active_intents": list(belief.active_intents),
        "last_tool_called": belief.last_tool_called,
        "last_search_count": belief.last_search_count,
        "last_search_ids": belief.last_search_ids,
        "last_search_context": belief.last_search_context,
        "last_property_data": belief.last_property_data,
        "last_shown_detail_id": belief.last_shown_detail_id,
        "pending_offer": belief.pending_offer,
        "scheduling_name": belief.scheduling_name,
        "scheduling_phone": belief.scheduling_phone,
        "scheduling_day": belief.scheduling_day,
        "scheduling_time": belief.scheduling_time,
        "scheduling_loop_count": belief.scheduling_loop_count,
        "turn_count": belief.turn_count,
        "history": belief.history[-5:],  # last 5 messages
    })


def _deserialize_belief(data: str | bytes, session_id: str) -> ConversationBeliefState:
    """Deserialize JSON from Redis back to belief state."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    d = json.loads(data)
    return ConversationBeliefState(
        session_id=session_id,
        operation=d.get("operation"),
        property_type=d.get("property_type"),
        zone=d.get("zone"),
        budget_max=d.get("budget_max"),
        bedrooms_min=d.get("bedrooms_min"),
        selected_property_id=d.get("selected_property_id"),
        active_intents=set(d.get("active_intents", [])),
        last_tool_called=d.get("last_tool_called"),
        last_search_count=d.get("last_search_count", 0),
        last_search_ids=d.get("last_search_ids", []),
        last_search_context=d.get("last_search_context", ""),
        last_property_data=d.get("last_property_data", ""),
        last_shown_detail_id=d.get("last_shown_detail_id"),
        pending_offer=d.get("pending_offer"),
        scheduling_name=d.get("scheduling_name", ""),
        scheduling_phone=d.get("scheduling_phone", ""),
        scheduling_day=d.get("scheduling_day", ""),
        scheduling_time=d.get("scheduling_time", ""),
        scheduling_loop_count=d.get("scheduling_loop_count", 0),
        turn_count=d.get("turn_count", 0),
        history=d.get("history", []),
    )


async def _get_redis():
    """Get Redis connection or None if unavailable."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.resolve_redis_url(), socket_connect_timeout=1)
        await r.ping()
        return r
    except Exception:
        return None
