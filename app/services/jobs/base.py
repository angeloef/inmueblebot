"""Job primitives: the JobDef record, per-tenant iteration, and result aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable
from uuid import UUID

from loguru import logger

from app.core.tenancy import tenant_scope

# A per-tenant handler returns a small dict of counters merged into the job summary.
TenantHandler = Callable[[UUID], Awaitable[dict]]
# A job handler runs the whole job (usually by calling for_each_tenant) and returns a summary.
JobHandler = Callable[[], Awaitable[dict]]


@dataclass(frozen=True)
class JobDef:
    """One scheduled job.

    ``cron`` is an APScheduler cron kwargs dict (e.g. ``{"hour": 9, "minute": 0}``). The
    scheduler builds a CronTrigger from it; the runner can also fire any job on demand.
    """

    name: str
    handler: JobHandler
    cron: dict
    description: str = ""
    catchup: bool = True  # run during the startup catch-up pass


@dataclass
class JobSummary:
    """Aggregated outcome of a job run, returned to the trigger endpoint / logs."""

    job: str
    tenants_processed: int = 0
    counters: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add(self, result: dict) -> None:
        for k, v in (result or {}).items():
            if isinstance(v, (int, float)):
                self.counters[k] = self.counters.get(k, 0) + v

    def as_dict(self) -> dict:
        return {
            "job": self.job,
            "tenants_processed": self.tenants_processed,
            "counters": self.counters,
            "errors": self.errors,
        }


async def for_each_tenant(job_name: str, per_tenant: TenantHandler) -> JobSummary:
    """Run ``per_tenant`` for every active tenant under its own RLS scope.

    Errors are isolated per tenant: one inmobiliaria failing never aborts the batch.
    """
    from app.services.tenant_service import list_operational_tenant_ids

    summary = JobSummary(job=job_name)
    # Leaf tenants only (sucursales + standalone). Excludes Enterprise org parents so
    # org-aware RLS doesn't make a parent re-process every child's rows (duplicate sends).
    tenant_ids = await list_operational_tenant_ids()
    for tid in tenant_ids:
        try:
            with tenant_scope(tid):
                result = await per_tenant(tid)
            summary.tenants_processed += 1
            summary.add(result)
        except Exception as exc:  # isolate per-tenant failures
            msg = f"tenant={tid}: {exc}"
            logger.error(f"[Job:{job_name}] {msg}")
            summary.errors.append(msg)
    logger.info(f"[Job:{job_name}] done — {summary.as_dict()}")
    return summary
