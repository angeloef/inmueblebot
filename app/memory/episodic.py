"""EpisodicMemory — past session summaries for cross-session recall.

Redis: episodic:{phone} — list of last 10 session summaries (TTL: 90d)
PostgreSQL: user_episodes table — full durable records.
"""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
settings = get_settings()
from app.db.session import async_session_factory
from app.db.models.user_episode import UserEpisode


async def save_episode(
    phone: str,
    session_id: str,
    summary: str,
    turn_count: int,
    search_criteria: dict | None = None,
    properties_viewed: list[int] | None = None,
    last_tool: str | None = None,
    intent_outcome: str | None = None,
) -> None:
    """Save a session episode to PostgreSQL and Redis cache."""
    # PostgreSQL (durable)
    async with async_session_factory() as session:
        episode = UserEpisode(
            phone=phone,
            session_id=session_id,
            summary=summary,
            turn_count=turn_count,
            search_criteria=search_criteria,
            properties_viewed=properties_viewed or [],
            last_tool_called=last_tool,
            intent_outcome=intent_outcome,
        )
        session.add(episode)
        await session.commit()

    # Redis cache (fast retrieval)
    redis = await _get_redis()
    if redis:
        key = f"episodic:{phone}"
        entry = json.dumps({
            "session_id": session_id,
            "summary": summary,
            "turn_count": turn_count,
            "search_criteria": search_criteria,
            "properties_viewed": properties_viewed,
            "timestamp": datetime.utcnow().isoformat(),
        })
        await redis.lpush(key, entry)
        await redis.ltrim(key, 0, 9)  # Keep last 10
        await redis.expire(key, 90 * 86400)  # 90 days TTL
        await redis.aclose()


async def get_episodes(phone: str, limit: int = 5) -> list[dict]:
    """Get recent session episodes for a user.

    Tries Redis first, falls back to PostgreSQL.
    """
    redis = await _get_redis()
    if redis:
        entries = await redis.lrange(f"episodic:{phone}", 0, limit - 1)
        await redis.aclose()
        if entries:
            return [json.loads(e if isinstance(e, str) else e.decode()) for e in entries]

    # PostgreSQL fallback
    async with async_session_factory() as session:
        result = await session.execute(
            select(UserEpisode)
            .where(UserEpisode.phone == phone)
            .order_by(UserEpisode.created_at.desc())
            .limit(limit)
        )
        episodes = result.scalars().all()
        return [
            {
                "session_id": e.session_id,
                "summary": e.summary,
                "turn_count": e.turn_count,
                "search_criteria": e.search_criteria,
                "properties_viewed": e.properties_viewed,
                "timestamp": e.created_at.isoformat() if e.created_at else "",
            }
            for e in episodes
        ]


async def get_last_episode(phone: str) -> Optional[dict]:
    """Get the most recent episode for a user."""
    episodes = await get_episodes(phone, limit=1)
    return episodes[0] if episodes else None


async def build_greeting_from_episodes(phone: str) -> str:
    """Build a personalized greeting based on past episodes.

    Returns empty string if no prior episodes found.
    """
    last = await get_last_episode(phone)
    if not last:
        return ""

    criteria = last.get("search_criteria") or {}
    viewed = last.get("properties_viewed") or []

    parts = ["¡Bienvenido de nuevo"]

    if criteria:
        op = criteria.get("operación", "")
        tipo = criteria.get("tipo", "")
        zona = criteria.get("zona", "")
        budget = criteria.get("presupuesto_máx", "")

        if op and tipo:
            parts.append(f"La última vez buscabas {tipo} en {op}")
        elif op:
            parts.append(f"La última vez buscabas {op}")

        if zona:
            parts.append(f"en {zona}")

        if budget:
            parts.append(f"con presupuesto de {budget}")

        if viewed:
            parts.append(f"y miraste {len(viewed)} propiedad(es)")

    parts.append("¿Seguís con esa búsqueda o ajustamos?")

    return " ".join(parts) + "."


async def _get_redis():
    """Get Redis connection or None if unavailable."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.resolve_redis_url(), socket_connect_timeout=1)
        await r.ping()
        return r
    except Exception:
        return None
