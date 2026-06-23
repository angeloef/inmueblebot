"""V4 BeliefStateV6 — extends V5 with last_sub_goals for KA1 perception.

Storage key is IDENTICAL to V3 (schema_version field differentiates).
V3 reading V6 data is safe: deserialize_v5 uses .get() on all fields and
ignores the extra last_sub_goals key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.routers.v3.belief import (
    BeliefStateV5,
    _get_redis,
    serialize_v5,
    deserialize_v5,
    load_belief_v5,
)


@dataclass
class BeliefStateV6(BeliefStateV5):
    """BeliefStateV5 + KA1 perception fields."""

    schema_version: int = 6
    # sub_goals from the last perceived turn (list of {intent, args_hint} dicts)
    last_sub_goals: list[dict[str, Any]] = field(default_factory=list)


def _promote_v5_to_v6(v5: BeliefStateV5) -> BeliefStateV6:
    """Promote a V5 belief to V6 in-memory, keeping all existing fields."""
    v6 = BeliefStateV6(session_id=v5.session_id)
    v6.__dict__.update(v5.__dict__)
    v6.schema_version = 6
    if not hasattr(v6, "last_sub_goals"):
        v6.last_sub_goals = []
    return v6


def serialize_v6(belief: BeliefStateV6) -> str:
    """Serialize V6 → JSON, extending V5 serialization with the extra field."""
    d = json.loads(serialize_v5(belief))
    d["schema_version"] = 6
    d["last_sub_goals"] = getattr(belief, "last_sub_goals", [])
    return json.dumps(d, ensure_ascii=False)


def deserialize_v6(raw: str | bytes, session_id: str) -> BeliefStateV6:
    """Deserialize JSON (from Redis) into a BeliefStateV6."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    d = json.loads(raw)
    v5 = deserialize_v5(raw, session_id)
    v6 = _promote_v5_to_v6(v5)
    v6.last_sub_goals = d.get("last_sub_goals", [])
    return v6


async def load_belief_v6(session_id: str) -> BeliefStateV6:
    """Load from Redis, migrating V4/V5 → V6 transparently.

    Caller MUST have called set_current_tenant(tenant_id) before this.
    Returns a fresh BeliefStateV6 on any failure.
    """
    from app.core.tenancy import tenant_redis_key

    key = tenant_redis_key("working", session_id)
    try:
        redis = await _get_redis()
        if redis:
            try:
                raw = await redis.get(key)
            finally:
                await redis.aclose()
            if raw:
                try:
                    d = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                    if d.get("schema_version", 4) >= 6:
                        return deserialize_v6(raw, session_id)
                    # V5 or older — load via V5 path then promote
                    v5 = await load_belief_v5(session_id)
                    return _promote_v5_to_v6(v5)
                except Exception as exc:
                    logger.warning(
                        "[V4] belief deserialize failed for {} — starting fresh: {}",
                        session_id, str(exc),
                    )
        else:
            v5 = await load_belief_v5(session_id)
            return _promote_v5_to_v6(v5)
    except Exception as exc:
        logger.warning("[V4] load_belief_v6 failed for {} — starting fresh: {}", session_id, str(exc))

    return BeliefStateV6(session_id=session_id)


async def save_belief_v6(belief: BeliefStateV6) -> None:
    """Persist a BeliefStateV6 under the same Redis key as V3/V5.

    Caller MUST have called set_current_tenant(tenant_id) before this.
    Fails silently — persistence failure must never break a turn.
    """
    from app.core.tenancy import tenant_redis_key
    from app.core.config import get_settings

    key = tenant_redis_key("working", belief.session_id)
    settings = get_settings()
    try:
        redis = await _get_redis()
        if redis:
            try:
                data = serialize_v6(belief)
                await redis.set(key, data, ex=settings.WORKING_MEMORY_TTL)
            finally:
                await redis.aclose()
        else:
            from app.core.belief_state import save_belief
            save_belief(belief)
    except Exception as exc:
        logger.warning("[V4] save_belief_v6 failed for {}: {}", belief.session_id, str(exc))
