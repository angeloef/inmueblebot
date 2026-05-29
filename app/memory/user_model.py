"""UserPersona — cross-session user preferences and behavior (Phase 7).

Redis: persona:{phone} — JSON blob with preferences, expertise, patterns.
"""

import json
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.core.identity import get_identity_key
settings = get_settings()


async def get_persona(phone: str) -> dict:
    """Get or create a user persona.

    Returns a dict with preferences, history, and behavior patterns.
    """
    redis = await _get_redis()
    if redis:
        data = await redis.get(f"persona:{get_identity_key() or phone}")
        await redis.aclose()
        if data:
            return json.loads(data if isinstance(data, str) else data.decode())

    # Default fresh persona
    return {
        "phone": phone,
        "created_at": datetime.utcnow().isoformat(),
        "preferred_zones": [],
        "preferred_types": [],
        "budget_range": None,
        "session_count": 0,
        "total_properties_viewed": 0,
        "last_operation": None,  # alquiler / venta
        "objections": [],  # patterns: "muy caro", "muy lejos"
        "interaction_tone": "neutral",  # formal, casual, rushed
    }


async def update_persona(phone: str, updates: dict) -> None:
    """Update a user persona with new data (accumulates, doesn't replace)."""
    persona = await get_persona(phone)

    # Accumulate session count
    if "session_count" in updates:
        persona["session_count"] += updates["session_count"]

    # Track viewed properties
    if "properties_viewed" in updates:
        persona["total_properties_viewed"] += len(updates["properties_viewed"])

    # Track preferred zones (most frequent)
    if "zone" in updates and updates["zone"]:
        zones = persona.setdefault("preferred_zones", [])
        zone = updates["zone"]
        # Simple frequency tracking
        found = False
        for z in zones:
            if isinstance(z, dict) and z.get("name") == zone:
                z["count"] += 1
                found = True
                break
        if not found:
            zones.append({"name": zone, "count": 1})
        # Keep top 3
        zones.sort(key=lambda x: x.get("count", 0), reverse=True)
        persona["preferred_zones"] = zones[:3]

    # Track preferred property types
    if "property_type" in updates and updates["property_type"]:
        types = persona.setdefault("preferred_types", [])
        ptype = updates["property_type"]
        found = False
        for t in types:
            if isinstance(t, dict) and t.get("name") == ptype:
                t["count"] += 1
                found = True
                break
        if not found:
            types.append({"name": ptype, "count": 1})
        types.sort(key=lambda x: x.get("count", 0), reverse=True)
        persona["preferred_types"] = types[:3]

    # Track objections
    if "objection" in updates and updates["objection"]:
        persona.setdefault("objections", []).append(updates["objection"])
        persona["objections"] = persona["objections"][-10:]

    # Last operation
    if "operation" in updates and updates["operation"]:
        persona["last_operation"] = updates["operation"]

    # Budget range
    if "budget_max" in updates and updates["budget_max"]:
        current = persona.get("budget_range")
        new_budget = updates["budget_max"]
        if current:
            persona["budget_range"] = (current + new_budget) / 2  # moving average
        else:
            persona["budget_range"] = new_budget

    persona["updated_at"] = datetime.utcnow().isoformat()

    # Persist
    redis = await _get_redis()
    if redis:
        await redis.set(f"persona:{get_identity_key() or phone}", json.dumps(persona), ex=settings.PERSONA_TTL)
        await redis.aclose()


async def build_personalized_context(phone: str) -> str:
    """Build a context string from persona for the LLM system prompt.

    Returns empty string if no persona data available.
    """
    persona = await get_persona(phone)

    if persona.get("session_count", 0) == 0:
        return ""

    parts = ["[PERFIL DEL USUARIO]"]

    zones = persona.get("preferred_zones", [])
    if zones:
        zone_str = ", ".join(
            f"{z.get('name', '?')} ({z.get('count', 0)}x)" for z in zones[:2]
        )
        parts.append(f"Zonas preferidas: {zone_str}")

    types = persona.get("preferred_types", [])
    if types:
        type_str = ", ".join(
            f"{t.get('name', '?')} ({t.get('count', 0)}x)" for t in types[:2]
        )
        parts.append(f"Tipos preferidos: {type_str}")

    budget = persona.get("budget_range")
    if budget:
        parts.append(f"Presupuesto habitual: ~${budget:,.0f}")

    op = persona.get("last_operation")
    if op:
        parts.append(f"Última operación: {op}")

    objections = persona.get("objections", [])
    if objections:
        recent = objections[-3:]
        parts.append(f"Objeciones recientes: {', '.join(recent)}")

    return "\n".join(parts) + "\n"


async def _get_redis():
    """Get Redis connection or None if unavailable."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.resolve_redis_url(), socket_connect_timeout=1)
        await r.ping()
        return r
    except Exception:
        return None
