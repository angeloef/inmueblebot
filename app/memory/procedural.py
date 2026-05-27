"""ProceduralMemory — skill execution tracking (Phase 7).

Tracks which skills were used, how often, and their success/failure patterns.
Redis: procedural:{phone} — JSON execution log.
"""

import json
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
settings = get_settings()


async def record_skill_use(
    phone: str, skill_name: str, success: bool, latency_ms: float = 0
) -> None:
    """Record a skill execution for a user."""
    redis = await _get_redis()
    if not redis:
        return

    key = f"procedural:{phone}"
    entry = json.dumps({
        "skill": skill_name,
        "success": success,
        "latency_ms": latency_ms,
        "timestamp": datetime.utcnow().isoformat(),
    })

    await redis.lpush(key, entry)
    await redis.ltrim(key, 0, 49)  # Keep last 50
    await redis.expire(key, 30 * 86400)  # 30 days TTL
    await redis.aclose()


async def get_skill_stats(phone: str) -> dict:
    """Get aggregated skill execution statistics for a user."""
    redis = await _get_redis()
    if not redis:
        return {}

    entries = await redis.lrange(f"procedural:{phone}", 0, 49)
    await redis.aclose()

    stats: dict[str, dict] = {}
    for e in entries:
        data = json.loads(e if isinstance(e, str) else e.decode())
        name = data.get("skill", "unknown")
        if name not in stats:
            stats[name] = {"count": 0, "successes": 0, "total_latency": 0}
        stats[name]["count"] += 1
        if data.get("success"):
            stats[name]["successes"] += 1
        stats[name]["total_latency"] += data.get("latency_ms", 0)

    # Add computed fields
    for name, s in stats.items():
        s["success_rate"] = s["successes"] / s["count"] if s["count"] > 0 else 0
        s["avg_latency_ms"] = s["total_latency"] / s["count"] if s["count"] > 0 else 0

    return stats


async def get_most_used_skill(phone: str) -> Optional[str]:
    """Get the most frequently used skill for a user."""
    stats = await get_skill_stats(phone)
    if not stats:
        return None
    return max(stats, key=lambda k: stats[k]["count"])


async def _get_redis():
    """Get Redis connection or None if unavailable."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.resolve_redis_url(), socket_connect_timeout=1)
        await r.ping()
        return r
    except Exception:
        return None
