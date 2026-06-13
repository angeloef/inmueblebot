"""Job: reporte ejecutivo mensual al dueño (Enterprise) por WhatsApp + dashboard.

Una vez por mes, a cada tenant RAÍZ (org Enterprise o standalone) le manda un resumen
ejecutivo del MES ANTERIOR. Para una org, las métricas son consolidadas (RLS org-aware ve
todas las sucursales). Corre a diario y de-dupea por mes vía el setting ``monthly_report_last``.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from loguru import logger

import app.services.billing_service as bs
from app.core.tenancy import tenant_scope
from app.services.analytics_service import compute_metrics
from app.services.jobs.base import JobSummary
from app.services.notification_dispatch import Dispatch, EventType, dispatch

JOB_NAME = "monthly_report"
LAST_SENT_SETTING = "monthly_report_last"
OWNER_PHONE_SETTING = "owner_phone"


def _money(n: int) -> str:
    return f"${int(n or 0):,.0f}".replace(",", ".")


def _build_text(company: str, period: date, m: dict) -> tuple[str, str]:
    f, c, ca = m["funnel"], m["cobranzas"], m["cartera"]
    mes = f"{period.month:02d}/{period.year}"
    lines = [
        f"📈 Reporte ejecutivo {mes} — {company}",
        "",
        "🎯 Embudo:",
        f"   Leads {f['leads']} → visitas {f['visits_scheduled']} → "
        f"realizadas {f['visits_done']} → cierres {f['closings']}",
        f"   Conversión lead→visita {f['rates']['lead_to_visit']}% · "
        f"asistencia {f['rates']['show_rate']}% · cierre {f['rates']['visit_to_close']}%",
        "",
        "💰 Cobranzas:",
        f"   Cobrado {_money(c['paid'])} de {_money(c['billed'])} ({c['pct_cobrado']}%)",
        f"   Morosidad {_money(c['morosidad_amount'])} ({c['overdue_count']} cobros) · "
        f"contratos por vencer {c['contracts_expiring']}",
        "",
        "🏠 Cartera:",
        f"   Disponibles {ca['available']} · cerradas {ca['closed']} · "
        f"sin consultas {ca['dead']} · antigüedad media {ca['avg_age_days']:.0f}d",
    ]
    text = "\n".join(lines)
    summary_line = (
        f"Leads {f['leads']} · cierres {f['closings']} · "
        f"cobrado {c['pct_cobrado']}% · morosos {c['overdue_count']}"
    )
    return text, summary_line


async def _per_root(tenant_id: UUID) -> dict:
    from app.db.models.tenant import Tenant
    from app.db.session import async_session_factory
    from app.services.tenant_service import get_tenant_setting, set_tenant_setting

    today = bs.today_ar()
    cur_start = bs.month_start(today)
    prev_start = bs.add_months(cur_start, -1)
    tag = f"{prev_start.year:04d}-{prev_start.month:02d}"

    last = await get_tenant_setting(tenant_id, LAST_SENT_SETTING)
    if last == tag:
        return {"skipped_already_sent": 1}

    async with async_session_factory() as s:
        tenant = await s.get(Tenant, tenant_id)
    company = (tenant.company_name or tenant.display_name) if tenant else "tu inmobiliaria"

    metrics = await compute_metrics(tenant_id, prev_start, cur_start, today)
    text, summary_line = _build_text(company, prev_start, metrics)
    owner_phone = await get_tenant_setting(tenant_id, OWNER_PHONE_SETTING)

    await dispatch(
        tenant_id,
        Dispatch(
            event=EventType.MONTHLY_REPORT,
            recipient_phone=owner_phone,
            dashboard_title="Reporte ejecutivo mensual",
            dashboard_body=summary_line,
            wa_text=text,
            dashboard_type="monthly_report",
            metadata={"period": tag},
        ),
    )
    await set_tenant_setting(tenant_id, LAST_SENT_SETTING, tag)
    return {"sent": 1}


async def run() -> dict:
    """Iterate ROOT tenants (orgs + standalones) under each one's scope."""
    from app.services.tenant_service import list_root_tenant_ids

    summary = JobSummary(job=JOB_NAME)
    for tid in await list_root_tenant_ids():
        try:
            with tenant_scope(tid):
                result = await _per_root(tid)
            summary.tenants_processed += 1
            summary.add(result)
        except Exception as exc:  # isolate per-tenant failures
            logger.error(f"[Job:{JOB_NAME}] tenant={tid}: {exc}")
            summary.errors.append(f"tenant={tid}: {exc}")
    logger.info(f"[Job:{JOB_NAME}] done — {summary.as_dict()}")
    return summary.as_dict()
