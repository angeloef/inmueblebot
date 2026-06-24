"""EpisodicMemory — past session summaries for cross-session recall.

Redis: episodic:{phone} — list of last 10 session summaries (TTL: 90d)
PostgreSQL: user_episodes table — full durable records.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select

from app.core.identity import get_identity_key
from app.core.config import get_settings
from app.core.tenancy import tenant_redis_key
settings = get_settings()
from app.db.session import async_session_factory
from app.db.models.user_episode import UserEpisode

logger = logging.getLogger(__name__)


async def _pg_available() -> bool:
    """Check if user_episodes table exists in PostgreSQL."""
    try:
        from sqlalchemy import text
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1 FROM user_episodes LIMIT 0"))
        return True
    except Exception:
        return False


async def _ensure_user_episodes_table() -> bool:
    """Create user_episodes table if it doesn't exist. Returns True if created."""
    try:
        from sqlalchemy import text
        async with async_session_factory() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS user_episodes (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(30) NOT NULL,
                    bsuid VARCHAR(100),
                    session_id VARCHAR(100) UNIQUE NOT NULL,
                    summary TEXT DEFAULT '',
                    turn_count INTEGER DEFAULT 0,
                    last_tool_called VARCHAR(50),
                    search_criteria JSONB,
                    properties_viewed JSONB DEFAULT '[]',
                    intent_outcome VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await session.commit()
        return True
    except Exception:
        return False


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
    # PostgreSQL (durable) — gracefully skip if table missing
    try:
        from app.core.tenancy import resolve_tenant_id
        async with async_session_factory() as session:
            episode = UserEpisode(
                # tenant_id REQUIRED: RLS WITH CHECK rejects NULL, and a NULL-tenant row would
                # be invisible to every tenant-scoped query. See seed.py / appointment_service.
                tenant_id=resolve_tenant_id(),
                phone=phone,
                bsuid=get_identity_key() or None,
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
    except Exception as exc:
        # Non-fatal: Redis cache below is still written. But log it — this previously
        # swallowed RLS rejections (NULL tenant_id) silently, hiding real failures.
        logger.warning(f"[EpisodicMemory] could not persist episode to PostgreSQL: {exc}")

    # Redis cache (fast retrieval)
    redis = await _get_redis()
    if redis:
        key = tenant_redis_key("episodic", get_identity_key() or phone)
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
    Gracefully handles missing user_episodes table.
    """
    redis = await _get_redis()
    if redis:
        entries = await redis.lrange(tenant_redis_key("episodic", get_identity_key() or phone), 0, limit - 1)
        await redis.aclose()
        if entries:
            return [json.loads(e if isinstance(e, str) else e.decode()) for e in entries]

    # PostgreSQL fallback — gracefully skip if table missing
    try:
        from app.core.tenancy import resolve_tenant_id
        async with async_session_factory() as session:
            identity_key = get_identity_key()
            # tenant_id filter is REQUIRED here: the Redis path is tenant-scoped via
            # tenant_redis_key(), but this fallback must not match a phone/bsuid across
            # tenants (RLS may not be applied on the pooled session's GUC). Without it,
            # two agencies sharing a contact phone would leak episodes between tenants.
            result = await session.execute(
                select(UserEpisode)
                .where(UserEpisode.tenant_id == resolve_tenant_id())
                .where((UserEpisode.bsuid == identity_key) | (UserEpisode.phone == phone))
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
    except Exception:
        return []


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
