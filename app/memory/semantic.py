"""SemanticMemory — zone knowledge graph and FAQ cache (Phase 7).

Redis: kgraph:zone:{name} → zone data JSON
PostgreSQL: zone_stats table for search aggregation.
"""

import json
from typing import Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.core.tenancy import tenant_redis_key
settings = get_settings()
from app.db.session import async_session_factory
from app.db.models.user_episode import ZoneStat


# Zone knowledge — static base data
ZONE_KNOWLEDGE = {
    "Centro": {
        "avg_price_alquiler": 85000,
        "avg_price_venta": 40000000,
        "property_count": 5,
        "amenities": ["agua corriente", "gas natural", "internet", "transporte"],
    },
    "UNAM": {
        "avg_price_alquiler": 50000,
        "avg_price_venta": 25000000,
        "property_count": 4,
        "amenities": ["cerca facultad", "colectivo", "internet", "zona estudiantil"],
    },
    "Barrio Schuster": {
        "avg_price_alquiler": 68000,
        "avg_price_venta": 25000000,
        "property_count": 5,
        "amenities": ["residencial", "árboles frutales", "patios grandes", "tranquilo"],
    },
    "Ruta 14": {
        "avg_price_alquiler": 62000,
        "avg_price_venta": 25000000,
        "property_count": 5,
        "amenities": ["frente ruta", "apto comercio", "quintas", "terrenos grandes"],
    },
}


async def get_zone_info(zone_name: str) -> Optional[dict]:
    """Get zone knowledge, enriched with Redis/PostgreSQL data."""
    zone_name = zone_name.strip()

    # Try Redis cache first — key MUST be tenant-scoped: zone names collide across
    # agencies (every agency can have a "Centro"); a bare key would serve one
    # tenant's cached prices/amenities to another.
    zone_key = tenant_redis_key("kgraph:zone", zone_name)
    redis = await _get_redis()
    if redis:
        data = await redis.get(zone_key)
        if data:
            await redis.aclose()
            return json.loads(data if isinstance(data, str) else data.decode())

    # Fallback to static knowledge + PostgreSQL stats
    base = ZONE_KNOWLEDGE.get(zone_name, {})
    if not base:
        return None

    # Enrich with search count from PostgreSQL
    async with async_session_factory() as session:
        result = await session.execute(
            select(ZoneStat).where(ZoneStat.zone_name == zone_name)
        )
        stat = result.scalars().first()
        if stat:
            base["search_count"] = stat.search_count
            base["dynamic_avg_alquiler"] = stat.avg_price_alquiler
            base["dynamic_avg_venta"] = stat.avg_price_venta

    # Cache in Redis for 1 hour
    if redis is None:
        redis = await _get_redis()
    if redis:
        await redis.set(
            zone_key,
            json.dumps(base),
            ex=3600,
        )
        await redis.aclose()

    return base


async def increment_zone_search(zone_name: str) -> None:
    """Increment the search counter for a zone."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ZoneStat).where(ZoneStat.zone_name == zone_name)
        )
        stat = result.scalars().first()

        if stat:
            stat.search_count += 1
        else:
            # tenant_id REQUIRED: RLS WITH CHECK rejects NULL, and a NULL-tenant row would
            # be invisible to every tenant-scoped query. See seed.py / appointment_service.
            from app.core.tenancy import resolve_tenant_id
            stat = ZoneStat(zone_name=zone_name, search_count=1, tenant_id=resolve_tenant_id())
            session.add(stat)

        await session.commit()


async def get_zone_comparison() -> str:
    """Build a comparison table of all zones."""
    lines = ["Comparativa de zonas en Oberá:\n"]
    for name, info in ZONE_KNOWLEDGE.items():
        lines.append(
            f"{name}:\n"
            f"  Alquiler prom: ${info['avg_price_alquiler']:,}/mes\n"
            f"  Venta prom: ${info['avg_price_venta']:,}\n"
            f"  {info['property_count']} propiedades\n"
            f"  {', '.join(info['amenities'][:3])}\n"
        )
    return "\n".join(lines)


async def _get_redis():
    """Get Redis connection or None if unavailable."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.resolve_redis_url(), socket_connect_timeout=1)
        await r.ping()
        return r
    except Exception:
        return None
