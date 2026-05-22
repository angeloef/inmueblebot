"""
v2.0 Property Graph Memory.

Stores user-property relationships in Redis:
- Viewed properties (with timestamps)
- Scheduled appointments
- Similar properties (computed offline, queried here)

Uses Redis Hashes + Sets — no RedisGraph dependency needed.
"""

from __future__ import annotations
import json
import time
from typing import Optional
from loguru import logger


# ── Key patterns ─────────────────────────────────────────────────────────

def _viewed_key(phone: str) -> str:
    return f"graph:user:{phone}:viewed"


def _scheduled_key(phone: str) -> str:
    return f"graph:user:{phone}:scheduled"


def _similar_key(property_id: str) -> str:
    return f"graph:property:{property_id}:similar"


# ── Viewed properties ────────────────────────────────────────────────────

async def record_property_view(phone: str, property_id: str, title: str = ""):
    """Record that a user viewed a property."""
    try:
        from app.core.memory import memory_manager
        r = await memory_manager._get_redis_with_retry()
        key = _viewed_key(phone)
        entry = json.dumps({
            "property_id": str(property_id),
            "title": title,
            "timestamp": time.time(),
        }, ensure_ascii=False)
        await r.lpush(key, entry)
        await r.ltrim(key, 0, 49)  # Keep last 50 views
        logger.debug(f"[GraphMemory] Recorded view: {phone[-4:]} -> prop {property_id}")
    except Exception as e:
        logger.warning(f"[GraphMemory] record_property_view failed: {e}")


async def get_viewed_properties(phone: str, limit: int = 10) -> list[dict]:
    """Get the user's recently viewed properties."""
    try:
        from app.core.memory import memory_manager
        r = await memory_manager._get_redis_with_retry()
        key = _viewed_key(phone)
        raw = await r.lrange(key, 0, limit - 1)
        return [json.loads(item) for item in raw]
    except Exception as e:
        logger.warning(f"[GraphMemory] get_viewed_properties failed: {e}")
        return []


# ── Scheduled appointments ────────────────────────────────────────────────

async def record_appointment(phone: str, appointment_id: str, property_id: str, date: str = ""):
    """Record a scheduled appointment."""
    try:
        from app.core.memory import memory_manager
        r = await memory_manager._get_redis_with_retry()
        key = _scheduled_key(phone)
        entry = json.dumps({
            "appointment_id": str(appointment_id),
            "property_id": str(property_id),
            "date": date,
            "timestamp": time.time(),
        }, ensure_ascii=False)
        await r.lpush(key, entry)
        await r.ltrim(key, 0, 19)
        logger.debug(f"[GraphMemory] Recorded appointment: {phone[-4:]}")
    except Exception as e:
        logger.warning(f"[GraphMemory] record_appointment failed: {e}")


async def get_scheduled_appointments(phone: str) -> list[dict]:
    """Get user's scheduled appointments from graph memory."""
    try:
        from app.core.memory import memory_manager
        r = await memory_manager._get_redis_with_retry()
        key = _scheduled_key(phone)
        raw = await r.lrange(key, 0, -1)
        return [json.loads(item) for item in raw]
    except Exception as e:
        logger.warning(f"[GraphMemory] get_scheduled_appointments failed: {e}")
        return []


# ── Similar properties ───────────────────────────────────────────────────

async def set_similar_properties(property_id: str, similar_ids: list[str]):
    """Store similar property relationships (computed offline, called from admin)."""
    try:
        from app.core.memory import memory_manager
        r = await memory_manager._get_redis_with_retry()
        key = _similar_key(str(property_id))
        await r.delete(key)
        if similar_ids:
            await r.sadd(key, *[str(sid) for sid in similar_ids])
        await r.expire(key, 86400 * 7)  # 7-day TTL
    except Exception as e:
        logger.warning(f"[GraphMemory] set_similar_properties failed: {e}")


async def get_similar_properties(property_id: str) -> list[str]:
    """Get properties similar to the given one."""
    try:
        from app.core.memory import memory_manager
        r = await memory_manager._get_redis_with_retry()
        key = _similar_key(str(property_id))
        members = await r.smembers(key)
        return list(members) if members else []
    except Exception as e:
        logger.warning(f"[GraphMemory] get_similar_properties failed: {e}")
        return []


# ── User graph context (for agent injection) ──────────────────────────────

async def get_user_graph_context(phone: str) -> dict:
    """Get a summary of user's graph relationships for the agent.

    Returns a dict suitable for injection into the system prompt.
    """
    views = await get_viewed_properties(phone, limit=5)
    appointments = await get_scheduled_appointments(phone)

    context = {}

    if views:
        viewed_ids = [v.get("property_id", "") for v in views]
        context["viewed_property_ids"] = viewed_ids
        # Get similar properties for the most recent view
        if viewed_ids:
            similar = await get_similar_properties(viewed_ids[0])
            if similar:
                context["similar_to_last_viewed"] = similar[:5]

    if appointments:
        context["scheduled_count"] = len(appointments)

    return context
