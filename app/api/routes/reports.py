"""Reportes ejecutivos mensuales (Enterprise) — embudo/cobranzas/cartera/demanda.

GET /reports?period=YYYY-MM devuelve las métricas del mes + el mes previo (para deltas).
Para el dueño en consolidado: totales de la org (RLS org-aware) + desglose por sucursal.
Para un gerente / sucursal entrada: las métricas de ese tenant.

El cálculo es en vivo (mes pedido + previo). El histórico estable lo persiste el job
``monthly_snapshot`` y lo consume el reporte ejecutivo por WhatsApp.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

import app.services.billing_service as bs
from app.api.deps import require_active_subscription
from app.db.models import TenantAccount
from app.services.analytics_service import compute_metrics

router = APIRouter(prefix="/reports", tags=["reports", "metrics"])

PERIODS_BACK = 12


def _series_point(period_d: date, metrics: dict) -> dict:
    f = metrics.get("funnel", {})
    c = metrics.get("cobranzas", {})
    billed = c.get("billed", 0) or 0
    morosidad = c.get("morosidad_amount", 0) or 0
    return {
        "month": f"{period_d.year:04d}-{period_d.month:02d}",
        "leads": int(f.get("leads", 0) or 0),
        "paid": int(c.get("paid", 0) or 0),
        "closings": int(f.get("closings", 0) or 0),
        # morosidad_pct is computed as-of today for all months (status snapshot, not month-end)
        "morosidad_pct": round((morosidad / billed) * 100, 1) if billed else 0.0,
    }


def _parse_period(period: str | None, today: date) -> date:
    """'YYYY-MM' → primer día del mes. Default: mes en curso."""
    if not period:
        return bs.month_start(today)
    try:
        y, m = period.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="period debe ser YYYY-MM") from exc


@router.get("/periods")
async def list_periods(_: TenantAccount = Depends(require_active_subscription)) -> dict:  # noqa: B008
    """Últimos 12 meses seleccionables (incluye el mes en curso)."""
    today = bs.today_ar()
    cur = bs.month_start(today)
    out = []
    for i in range(PERIODS_BACK):
        m = bs.add_months(cur, -i)
        out.append({"period": f"{m.year:04d}-{m.month:02d}",
                    "is_current": i == 0})
    return {"periods": out}


@router.get("")
async def get_report(
    period: str | None = Query(default=None),
    account: TenantAccount = Depends(require_active_subscription),  # noqa: B008
) -> dict:
    today = bs.today_ar()
    cur_start = _parse_period(period, today)
    cur_end = bs.add_months(cur_start, 1)
    prev_start = bs.add_months(cur_start, -1)
    prev_end = cur_start
    period_str = f"{cur_start.year:04d}-{cur_start.month:02d}"

    is_org = bool(getattr(account, "is_org", False))
    active_branch = getattr(account, "active_branch_id", None)

    # Consolidado del dueño: totales de la org (RLS org-aware) + por sucursal.
    if is_org and active_branch is None:
        from app.services.tenant_service import list_branches

        org_id = account.tenant_id
        totals = await compute_metrics(org_id, cur_start, cur_end, today)
        totals_prev = await compute_metrics(org_id, prev_start, prev_end, today)

        branches = []
        for b in await list_branches(org_id):
            branches.append({
                "branch_id": str(b.id),
                "name": b.display_name,
                "metrics": await compute_metrics(b.id, cur_start, cur_end, today),
                "prev": await compute_metrics(b.id, prev_start, prev_end, today),
            })
        return {
            "period": period_str, "scope": "org",
            "totals": totals, "totals_prev": totals_prev, "branches": branches,
        }

    # Sucursal / standalone / dueño que entró a una sucursal.
    tid = getattr(account, "effective_tenant_id", account.tenant_id)
    return {
        "period": period_str, "scope": "branch",
        "metrics": await compute_metrics(tid, cur_start, cur_end, today),
        "prev": await compute_metrics(tid, prev_start, prev_end, today),
    }


@router.get("/trend")
async def get_trend(
    account: TenantAccount = Depends(require_active_subscription),
) -> dict:
    today = bs.today_ar()
    cur_start = bs.month_start(today)
    months = [bs.add_months(cur_start, -i) for i in range(PERIODS_BACK - 1, -1, -1)]
    period_str = f"{cur_start.year:04d}-{cur_start.month:02d}"

    is_org = bool(getattr(account, "is_org", False))
    active_branch = getattr(account, "active_branch_id", None)

    if is_org and active_branch is None:
        org_id = account.tenant_id
        series = [
            _series_point(m, await compute_metrics(org_id, m, bs.add_months(m, 1), today))
            for m in months
        ]
        return {"period": period_str, "scope": "org", "series": series}

    tid = getattr(account, "effective_tenant_id", account.tenant_id)
    series = [
        _series_point(m, await compute_metrics(tid, m, bs.add_months(m, 1), today))
        for m in months
    ]
    return {"period": period_str, "scope": "branch", "series": series}
