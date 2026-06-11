"""Per-user usage limits — cost-drain protection for the V3 client side.

Enforces a daily message cap per WhatsApp identity at the V3 engine boundary.
Redis-backed and tenant-namespaced, with an in-process fallback counter so the
cap still bounds spend during a Redis outage — the global OpenAI limiter fails
open, this one does NOT (that is the "keep per-user limits as a floor" decision).

The counter is keyed by calendar day in the tenant's timezone and auto-expires at
local midnight. A tenant resuming a capped conversation calls ``reset_daily`` to
hand the user a fresh allotment immediately.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger

# Fallback timezone when a tenant's configured tz is missing/invalid.
_DEFAULT_TZ = "America/Argentina/Buenos_Aires"

# In-process fallback counter: redis_key -> (day_str, count). Used only when Redis
# is unreachable. Bounded by pruning so a long outage can't grow it without limit.
_local_counts: dict[str, tuple[str, int]] = {}
_LOCAL_MAX_KEYS = 5000


def _tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or _DEFAULT_TZ)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


def _today_str(tz_name: str) -> str:
    return datetime.now(_tz(tz_name)).strftime("%Y-%m-%d")


def _seconds_until_midnight(tz_name: str) -> int:
    tz = _tz(tz_name)
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(60, int((tomorrow - now).total_seconds()))


def _daily_key(identity: str, day: str) -> str:
    """Tenant-namespaced Redis key for one identity's per-day counter."""
    from app.core.tenancy import tenant_redis_key

    return tenant_redis_key("daily_msg", day, identity)


def _local_incr(key: str, day: str) -> int:
    cur = _local_counts.get(key)
    if cur is None or cur[0] != day:
        _local_counts[key] = (day, 1)
        if len(_local_counts) > _LOCAL_MAX_KEYS:
            stale = [k for k, v in _local_counts.items() if v[0] != day]
            for k in stale[:1000]:
                _local_counts.pop(k, None)
        return 1
    count = cur[1] + 1
    _local_counts[key] = (day, count)
    return count


async def incr_daily_count(identity: str, tz_name: str = _DEFAULT_TZ) -> int:
    """Increment and return today's message count for ``identity``.

    Caller MUST have set the tenant ContextVar so the key is tenant-scoped.
    Uses Redis ``INCR`` + a midnight TTL; falls back to an in-process counter when
    Redis is unreachable so the cap keeps bounding cost during an outage.
    """
    day = _today_str(tz_name)
    key = _daily_key(identity, day)
    try:
        from app.routers.v3.belief import _get_redis

        redis = await _get_redis()
        if redis:
            try:
                count = int(await redis.incr(key))
                if count == 1:
                    await redis.expire(key, _seconds_until_midnight(tz_name))
                return count
            finally:
                await redis.aclose()
    except Exception as exc:
        logger.debug("[UsageLimits] Redis incr failed, using local fallback: {}", str(exc))
    return _local_incr(key, day)


async def reset_daily(identity: str, tz_name: str = _DEFAULT_TZ) -> None:
    """Clear today's counter for ``identity`` (called when a tenant resumes the bot).

    Caller MUST have set the tenant ContextVar so the key matches incr_daily_count.
    """
    day = _today_str(tz_name)
    key = _daily_key(identity, day)
    _local_counts.pop(key, None)
    try:
        from app.routers.v3.belief import _get_redis

        redis = await _get_redis()
        if redis:
            try:
                await redis.delete(key)
            finally:
                await redis.aclose()
    except Exception as exc:
        logger.debug("[UsageLimits] Redis reset failed (non-fatal): {}", str(exc))
