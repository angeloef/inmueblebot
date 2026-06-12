"""In-process scheduler (APScheduler) that fires the proactive-notification jobs.

Started from the FastAPI lifespan when ``ENABLE_SCHEDULER`` is set. On Render free the web
service sleeps on inactivity and APScheduler will NOT fire while asleep — so on startup we
run a one-shot **catch-up** pass (``SCHEDULER_CATCHUP_ON_START``) over every idempotent job
to cover the window that was missed. The cron triggers then handle the steady state while
the service is awake.

A single module-level scheduler instance is reused (idempotent start). Job handlers are the
ones in :mod:`app.services.jobs.registry`.
"""

from __future__ import annotations

import asyncio

from loguru import logger

_scheduler = None  # type: ignore[var-annotated]  # AsyncIOScheduler | None


def _build_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    from app.services.jobs.registry import JOBS
    from app.services.jobs.runner import run_job

    scheduler = AsyncIOScheduler(timezone="UTC")

    for job in JOBS:
        async def _runner(name: str = job.name) -> None:
            try:
                await run_job(name)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"[Scheduler] job '{name}' failed: {exc}")

        scheduler.add_job(
            _runner,
            trigger=CronTrigger(timezone="UTC", **job.cron),
            id=job.name,
            name=job.description or job.name,
            misfire_grace_time=3600,  # tolerate a late fire after a wake-up
            coalesce=True,            # collapse missed runs into one
            replace_existing=True,
        )
        logger.info(f"[Scheduler] registered job '{job.name}' cron={job.cron}")

    return scheduler


async def _run_catchup() -> None:
    """Run the idempotent catch-up pass shortly after boot (off the critical path)."""
    from app.services.jobs.runner import run_all

    try:
        results = await run_all(catchup_only=True)
        logger.info(f"[Scheduler] startup catch-up complete: {results}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[Scheduler] startup catch-up failed: {exc}")


def start_scheduler() -> None:
    """Start the scheduler and kick off the catch-up pass. Idempotent."""
    global _scheduler
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.ENABLE_SCHEDULER:
        logger.info("[Scheduler] ENABLE_SCHEDULER=False — not starting")
        return
    if _scheduler is not None and _scheduler.running:
        logger.info("[Scheduler] already running")
        return

    _scheduler = _build_scheduler()
    _scheduler.start()
    logger.info("[Scheduler] started")

    if settings.SCHEDULER_CATCHUP_ON_START:
        # Defer slightly so startup (DB warmup, etc.) settles before the catch-up batch.
        async def _delayed_catchup() -> None:
            await asyncio.sleep(15)
            await _run_catchup()

        asyncio.create_task(_delayed_catchup())


def shutdown_scheduler() -> None:
    """Stop the scheduler on app shutdown. Idempotent."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] stopped")
    _scheduler = None
