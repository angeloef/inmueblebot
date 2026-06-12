"""Run jobs on demand (manual trigger / external-cron fallback) and the catch-up pass."""

from __future__ import annotations

from loguru import logger

from app.services.jobs.registry import JOBS, get_job


async def run_job(name: str) -> dict:
    """Run a single registered job by name. Returns its summary dict.

    Raises ``KeyError`` if the job name is unknown (callers map this to 404).
    """
    job = get_job(name)
    if job is None:
        raise KeyError(name)
    logger.info(f"[Jobs] running '{name}' on demand")
    return await job.handler()


async def run_all(catchup_only: bool = False) -> dict:
    """Run every job once (used by the startup catch-up pass and the 'run all' trigger).

    With ``catchup_only=True`` only jobs flagged ``catchup`` run. Errors in one job never
    stop the others.
    """
    results: dict[str, dict] = {}
    for job in JOBS:
        if catchup_only and not job.catchup:
            continue
        try:
            results[job.name] = await job.handler()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"[Jobs] '{job.name}' raised during run_all: {exc}")
            results[job.name] = {"job": job.name, "error": str(exc)}
    return results
