"""Manual / external-cron trigger for the scheduled-jobs engine.

The in-process APScheduler (``app.workers.scheduler``) is the primary driver, but on Render
free the web service sleeps and may miss fires. This protected endpoint lets an external
cron (cron-job.org, GitHub Actions, an uptime pinger) poke a specific job — or all of them —
as a belt-and-suspenders fallback. Jobs are idempotent, so an extra poke is harmless.

Auth: a shared secret in the ``X-Jobs-Secret`` header must equal ``settings.JOBS_SECRET``.
If ``JOBS_SECRET`` is unset the endpoint is disabled (503) so it can't be hit unprotected.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _authorize(provided: str | None) -> None:
    secret = get_settings().JOBS_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="Jobs endpoint disabled (JOBS_SECRET unset)")
    if not provided or provided != secret:
        raise HTTPException(status_code=403, detail="Invalid jobs secret")


@router.post("/run")
async def run(name: str | None = None, x_jobs_secret: str | None = Header(default=None)) -> dict:
    """Run one job (``?name=visit_reminder``) or all jobs (no name). Returns summaries."""
    _authorize(x_jobs_secret)
    from app.services.jobs.runner import run_all, run_job

    if name:
        try:
            return {"ok": True, "result": await run_job(name)}
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job '{name}'")
    return {"ok": True, "results": await run_all()}
