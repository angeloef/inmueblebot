"""Job: snapshot mensual de KPIs por sucursal (Enterprise — reportes ejecutivos).

Para cada tenant operativo (sucursal/standalone) guarda una 'foto' de las métricas del MES
ANTERIOR en ``metric_snapshots`` (upsert idempotente por (tenant, period)). Corre a diario;
recalcular el mismo mes simplemente actualiza la foto, así que es seguro re-correr.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert

import app.services.billing_service as bs
from app.core.tenancy import tenant_scope
from app.db.models.metric_snapshot import MetricSnapshot
from app.db.session import async_session_factory
from app.services.analytics_service import compute_metrics
from app.services.jobs.base import JobSummary, for_each_tenant

JOB_NAME = "monthly_snapshot"


async def _per_tenant(tenant_id: UUID) -> dict:
    today = bs.today_ar()
    cur_start = bs.month_start(today)
    prev_start = bs.add_months(cur_start, -1)

    metrics = await compute_metrics(tenant_id, prev_start, cur_start, today)

    with tenant_scope(tenant_id):
        async with async_session_factory() as s:
            stmt = pg_insert(MetricSnapshot).values(
                tenant_id=tenant_id, period=prev_start, metrics=metrics,
            ).on_conflict_do_update(
                index_elements=["tenant_id", "period"],
                set_={"metrics": metrics},
            )
            await s.execute(stmt)
            await s.commit()
    return {"snapshotted": 1}


async def run() -> dict:
    summary: JobSummary = await for_each_tenant(JOB_NAME, _per_tenant)
    return summary.as_dict()
