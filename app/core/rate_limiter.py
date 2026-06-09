"""
Redis-based global rate limiter for OpenAI API calls.

Uses a sliding window counter stored in Redis.  When Redis is
unavailable it degrades gracefully — the check always passes,
allowing the call to proceed without rate limiting.

Usage:

    from app.core.rate_limiter import rate_limiter

    if not await rate_limiter.check_global():
        logger.warning("Global rate limit exceeded — dropping request")
        return
"""

import logging
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Global sliding-window rate limiter backed by Redis."""

    # Default: 50 requests per minute for the OpenAI API.
    # This should be below the OpenAI tier limit so the bot never
    # triggers a 429 from OpenAI itself.
    _DEFAULT_MAX_RPM = 50

    def __init__(self) -> None:
        self._max_rpm: int = self._DEFAULT_MAX_RPM

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_global(self) -> bool:
        """Return ``True`` if the request is *within* the rate limit.

        Returns ``True`` (allow) when Redis is unreachable so the bot
        keeps working — without rate limiting — until Redis recovers.
        """
        try:
            from app.core.memory import memory_manager

            r = await memory_manager._get_redis()
        except Exception:
            logger.debug("[RateLimiter] Redis unavailable — allowing request")
            return True

        key = "rate_limit:global"
        now = time.time()
        window_start = now - 60.0

        try:
            # Remove entries older than 60 seconds (sliding window)
            await r.zremrangebyscore(key, 0, window_start)

            # Count remaining entries in the window
            count = await r.zcard(key)
            if count >= self._max_rpm:
                logger.warning(
                    "[RateLimiter] Global rate limit hit: %d >= %d RPM",
                    count + 1,
                    self._max_rpm,
                )
                return False

            # Add current request timestamp
            await r.zadd(key, {str(now): now})
            await r.expire(key, 60)
            return True

        except Exception as e:
            logger.debug("[RateLimiter] Redis error during check — allowing: %s", e)
            return True

    async def check_key(
        self, key: str, max_count: int, window_seconds: int
    ) -> bool:
        """Per-key sliding-window limit. ``True`` = within limit (allow).

        Unlike ``check_global`` (one shared bucket), this rate-limits an arbitrary
        key independently — e.g. ``f"billing:subscribe:{tenant_id}"`` so one tenant
        can't spam an endpoint without affecting others. Degrades open (returns
        ``True``) when Redis is unreachable, matching ``check_global``.
        """
        try:
            from app.core.memory import memory_manager

            r = await memory_manager._get_redis()
        except Exception:
            logger.debug("[RateLimiter] Redis unavailable — allowing %s", key)
            return True

        redis_key = f"rate_limit:{key}"
        now = time.time()
        window_start = now - float(window_seconds)

        try:
            await r.zremrangebyscore(redis_key, 0, window_start)
            count = await r.zcard(redis_key)
            if count >= max_count:
                logger.warning(
                    "[RateLimiter] key limit hit: %s (%d >= %d / %ds)",
                    key, count, max_count, window_seconds,
                )
                return False
            await r.zadd(redis_key, {f"{now}:{count}": now})
            await r.expire(redis_key, window_seconds)
            return True
        except Exception as e:
            logger.debug("[RateLimiter] Redis error on %s — allowing: %s", key, e)
            return True

    async def get_remaining(self) -> int:
        """Return how many requests are still available in the current window.

        Returns ``self._max_rpm`` when Redis is unavailable.
        """
        try:
            from app.core.memory import memory_manager

            r = await memory_manager._get_redis()
        except Exception:
            return self._max_rpm

        key = "rate_limit:global"
        now = time.time()
        try:
            await r.zremrangebyscore(key, 0, now - 60)
            count = await r.zcard(key)
            return max(0, self._max_rpm - count)
        except Exception:
            return self._max_rpm


# Singleton instance
rate_limiter = RateLimiter()
