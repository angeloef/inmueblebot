"""
v2.0 Redis Message Queue.

Durable task queue for async chat processing.
Enqueues webhook messages to Redis List, dequeued by worker processes.
Survives server restarts — messages persist in Redis until processed.
"""

from __future__ import annotations
import json
import time
import asyncio
from typing import Optional
import redis.asyncio as redis
from loguru import logger

from app.core.config import get_settings

# ── Queue keys ────────────────────────────────────────────────────────────

QUEUE_KEY = "inmueblebot:message_queue"
USER_LOCK_PREFIX = "inmueblebot:user_lock:"
USER_LOCK_TTL = 30  # seconds — auto-release if worker crashes

# ── Queue client ──────────────────────────────────────────────────────────

_queue: Optional[redis.Redis] = None


async def _get_queue() -> redis.Redis:
    """Lazy-init Redis client for the queue."""
    global _queue
    if _queue is None:
        settings = get_settings()
        redis_url = settings.resolve_redis_url()
        _queue = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
        )
        await _queue.ping()
        logger.info("[MessageQueue] Redis connected")
    return _queue


# ── Enqueue (called from webhook) ─────────────────────────────────────────

async def enqueue_message(phone: str, text: str, media_url: Optional[str] = None) -> bool:
    """Enqueue a message for async processing. Returns True on success."""
    try:
        r = await _get_queue()
        task = json.dumps({
            "phone": phone,
            "text": text,
            "media_url": media_url,
            "timestamp": time.time(),
        }, ensure_ascii=False)
        await r.lpush(QUEUE_KEY, task)
        logger.debug(f"[MessageQueue] Enqueued message from {phone[-4:]}: {text[:30]}...")
        return True
    except Exception as e:
        logger.error(f"[MessageQueue] Enqueue failed: {e}")
        return False


# ── Dequeue (called from worker) ──────────────────────────────────────────

async def dequeue_message(timeout: int = 5) -> Optional[dict]:
    """Block and wait for the next message. Returns None on timeout."""
    try:
        r = await _get_queue()
        result = await r.brpop(QUEUE_KEY, timeout=timeout)
        if result is None:
            return None
        _, raw = result
        return json.loads(raw)
    except Exception as e:
        logger.error(f"[MessageQueue] Dequeue failed: {e}")
        await asyncio.sleep(1)
        return None


# ── Queue depth (for health checks) ───────────────────────────────────────

async def queue_depth() -> int:
    """Return current queue length."""
    try:
        r = await _get_queue()
        return await r.llen(QUEUE_KEY)
    except Exception:
        return -1


# ── Per-user locking (session affinity) ───────────────────────────────────

async def acquire_user_lock(phone: str) -> bool:
    """Try to acquire a per-user lock. Returns True if acquired."""
    try:
        r = await _get_queue()
        key = f"{USER_LOCK_PREFIX}{phone}"
        acquired = await r.set(key, "1", nx=True, ex=USER_LOCK_TTL)
        return bool(acquired)
    except Exception:
        return True  # If Redis is down, allow processing (fail open)


async def release_user_lock(phone: str):
    """Release a per-user lock."""
    try:
        r = await _get_queue()
        key = f"{USER_LOCK_PREFIX}{phone}"
        await r.delete(key)
    except Exception:
        pass


async def refresh_user_lock(phone: str):
    """Extend the TTL of a per-user lock (call periodically during long processing)."""
    try:
        r = await _get_queue()
        key = f"{USER_LOCK_PREFIX}{phone}"
        await r.expire(key, USER_LOCK_TTL)
    except Exception:
        pass


# ── Health ────────────────────────────────────────────────────────────────

async def check_health() -> dict:
    """Health check for the message queue."""
    try:
        r = await _get_queue()
        await r.ping()
        depth = await queue_depth()
        return {"status": "healthy", "queue_depth": depth}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:100]}
