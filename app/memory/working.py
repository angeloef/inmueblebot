"""WorkingMemory — current conversation state with Redis persistence (Phase 7).

Wraps ConversationBeliefState with Redis caching (TTL: 1 hour).
Falls back to in-memory dict when Redis is unavailable.
"""

import json
from typing import Optional
from loguru import logger

from app.core.belief_state import (
    ConversationBeliefState,
    _session_store as _fallback_store,
)
from app.core.config import get_settings
settings = get_settings()


async def save_working_memory(belief: ConversationBeliefState) -> None:
    """Persist working memory to Redis with 24-hour TTL."""
    key = f"working:{belief.session_id}"
    data = _serialize_belief(belief)

    redis = await _get_redis()
    if redis:
        await redis.set(key, data, ex=settings.WORKING_MEMORY_TTL)
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
    if belief.turn_count == 0:
        # Context recovery: check MemoryManager for old context (24h TTL)
        try:
            from app.core.memory import MemoryManager
            mm = MemoryManager()
            context = await mm.get_user_context(session_id)
            if context and context.get("last_search_criteria"):
                lsc = context["last_search_criteria"]
                extracted = lsc.get("extracted_prefs", {})
                if extracted.get("operation_type") and not belief.operation:
                    belief.operation = extracted["operation_type"]
                if extracted.get("location_preferences") and not belief.zone:
                    belief.zone = extracted["location_preferences"]
                if extracted.get("property_type") and not belief.property_type:
                    if isinstance(extracted["property_type"], list):
                        belief.property_type = extracted["property_type"][0]
                    else:
                        belief.property_type = extracted["property_type"]
                if extracted.get("bedrooms") and belief.bedrooms_min is None:
                    belief.bedrooms_min = int(extracted["bedrooms"])
                if belief.operation or belief.zone or belief.property_type:
                    logger.info(f"[WorkingMemory] Context recovered from MemoryManager for {session_id}")
        except Exception:
            pass
        return None  # Fresh state or recovery failed
    return belief


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
        "search_history": belief.search_history[-3:],
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
        "last_updated_at": belief.last_updated_at,
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
        search_history=d.get("search_history", []),
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
        last_updated_at=d.get("last_updated_at", 0.0),
    )


async def _get_redis():
    """Get Redis connection via MemoryManager connection pool for efficiency."""
    try:
        from app.core.memory import MemoryManager
        mm = MemoryManager()
        r = await mm._get_redis_with_retry()
        return r
    except Exception:
        return None
