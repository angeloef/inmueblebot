"""
v2.0 Chat Worker — Async message processor.

Dequeues messages from Redis queue, processes them through the
RealEstateAgent, and sends responses via WhatsApp.

Run as: python -m app.workers.chat_worker
Or via Docker: docker compose up chat_worker
"""

from __future__ import annotations
import asyncio
import json
import signal
import sys
import time
from loguru import logger

from app.core.message_queue import (
    dequeue_message,
    acquire_user_lock,
    release_user_lock,
    refresh_user_lock,
    check_health as queue_health,
)
from app.core.config import get_settings

# ── Worker state ──────────────────────────────────────────────────────────

_running = True
_processing_count = 0
_start_time = time.time()
_HEARTBEAT_INTERVAL = 30  # seconds


# ── Main worker loop ──────────────────────────────────────────────────────

async def _process_one_message(task: dict):
    """Process a single message from the queue."""
    import app.agents.real_estate_agent as agent_module
    from app.integrations.whatsapp import whatsapp_client

    phone = task.get("phone", "")
    text = task.get("text", "")
    media_url = task.get("media_url")

    if not phone or not text:
        logger.warning(f"[Worker] Skipping invalid task: {task}")
        return

    # Acquire per-user lock (session affinity)
    acquired = await acquire_user_lock(phone)
    if not acquired:
        logger.info(f"[Worker] User {phone[-4:]} locked by another worker, re-queuing")
        from app.core.message_queue import enqueue_message
        await enqueue_message(phone, text, media_url)
        await asyncio.sleep(1)  # small delay before retry
        return

    try:
        global _processing_count
        _processing_count += 1

        logger.info(f"[Worker] Processing: {phone[-4:]}: {text[:50]}...")

        start = time.time()
        agent = agent_module.real_estate_agent

        result = await agent.process_turn(
            phone=phone,
            user_message=text,
        )

        turn_time = time.time() - start
        logger.info(
            f"[Worker] Done: {phone[-4:]} | {turn_time:.1f}s | "
            f"tools={result.get('tools_used', [])}"
        )

        # Send response via WhatsApp
        response_text = (result.get("response_text") or "").strip()
        if response_text:
            from app.utils.sanitizer import sanitize_bot_response
            text_to_send = sanitize_bot_response(response_text)
            await whatsapp_client.send_message(to=phone, message=text_to_send)
            logger.info(f"[Worker] Sent response to {phone[-4:]} ({len(text_to_send)} chars)")

    except Exception as e:
        logger.error(f"[Worker] Error processing message from {phone[-4:]}: {e}")
    finally:
        _processing_count -= 1
        await release_user_lock(phone)


async def run_worker(worker_id: int = 0):
    """Main worker loop — blocks forever dequeueing and processing."""
    global _running

    logger.info(f"[Worker-{worker_id}] Starting chat worker...")

    # Health check on startup
    health = await queue_health()
    logger.info(f"[Worker-{worker_id}] Queue health: {health}")

    heartbeat_task = asyncio.create_task(_heartbeat_loop(worker_id))

    try:
        while _running:
            task = await dequeue_message(timeout=5)
            if task is None:
                continue  # timeout, try again

            await _process_one_message(task)

    except asyncio.CancelledError:
        logger.info(f"[Worker-{worker_id}] Cancelled")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        logger.info(f"[Worker-{worker_id}] Shut down")


async def _heartbeat_loop(worker_id: int):
    """Periodic heartbeat log for monitoring."""
    while _running:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        try:
            depth = await queue_health()
            uptime = time.time() - _start_time
            logger.info(
                f"[Worker-{worker_id}] heartbeat | uptime={uptime:.0f}s | "
                f"processing={_processing_count} | queue={depth.get('queue_depth', '?')}"
            )
        except Exception as e:
            logger.warning(f"[Worker-{worker_id}] heartbeat failed: {e}")


# ── Signal handling ───────────────────────────────────────────────────────

def _handle_signal(signum, frame):
    global _running
    logger.info(f"[Worker] Received signal {signum}, shutting down...")
    _running = False


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    """Entry point for the worker process."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    worker_id = 0
    try:
        asyncio.run(run_worker(worker_id))
    except KeyboardInterrupt:
        logger.info("[Worker] Keyboard interrupt, exiting")
    logger.info("[Worker] Exited cleanly")


if __name__ == "__main__":
    main()
