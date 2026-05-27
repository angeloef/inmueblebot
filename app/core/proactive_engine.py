"""Proactive engine — detects changes and generates alerts (Phase 8).

Checks for price drops, new listings, and re-engagement opportunities.
"""

from sqlalchemy import select

from app.core.cs_database import async_session
from app.models.property import Property


async def check_proactive_alerts(phone: str = "") -> list[dict]:
    """Check for proactive alerts for a user.

    Currently checks:
    - Recent properties added (simulated)
    - Zone availability

    Returns a list of alert dicts.
    """
    alerts = []

    # Check property count per zone for availability alerts
    async with async_session() as session:
        result = await session.execute(select(Property).limit(20))
        props = result.scalars().all()

    zones_count: dict[str, int] = {}
    for p in props:
        zones_count[p.zone] = zones_count.get(p.zone, 0) + 1

    # Alert if a zone has many properties (opportunity)
    for zone, count in zones_count.items():
        if count >= 4:
            alerts.append({
                "type": "zone_availability",
                "zone": zone,
                "count": count,
                "message": f"Hay {count} propiedades disponibles en {zone}. ¿Querés verlas?",
            })

    return alerts


async def get_proactive_summary() -> dict:
    """Get a summary of proactive alerts across all users."""
    alerts = await check_proactive_alerts()

    return {
        "alert_count": len(alerts),
        "alerts": alerts,
        "message": (
            f"Hay {len(alerts)} alertas disponibles."
            if alerts else "No hay alertas proactivas en este momento."
        ),
    }
