"""Job: weekly owner report (Profesional 🔜) — leads, visits, top properties, cobranzas.

Sent to the agency owner (``owner_phone`` tenant setting) once per ISO week. The job runs
daily and de-dupes per week via the ``weekly_report_last`` tenant setting (stores the week's
Monday), so it fires the first time it runs on/after Monday — robust to the Render-free
sleep that could skip the exact Monday fire.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

import app.services.billing_service as bs
from app.services.jobs.base import JobSummary, for_each_tenant
from app.services.notification_dispatch import Dispatch, EventType

JOB_NAME = "weekly_report"
LAST_SENT_SETTING = "weekly_report_last"
OWNER_PHONE_SETTING = "owner_phone"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _this_week_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _money(n: int) -> str:
    return f"${int(n or 0):,.0f}".replace(",", ".")


async def _per_tenant(tenant_id: UUID) -> dict:
    from app.services.tenant_service import get_tenant_setting, set_tenant_setting

    today = bs.today_ar()
    monday = _this_week_monday(today)

    last_raw = await get_tenant_setting(tenant_id, LAST_SENT_SETTING)
    if last_raw:
        try:
            if date.fromisoformat(last_raw) >= monday:
                return {"skipped_already_sent": 1}
        except ValueError:
            pass

    report = await _build_report(tenant_id, today)
    owner_phone = await get_tenant_setting(tenant_id, OWNER_PHONE_SETTING)

    from app.services.notification_dispatch import dispatch
    await dispatch(
        tenant_id,
        Dispatch(
            event=EventType.WEEKLY_REPORT,
            recipient_phone=owner_phone,
            dashboard_title="Reporte semanal",
            dashboard_body=report["summary_line"],
            wa_text=report["text"],
            dashboard_type="weekly_report",
            metadata={"week_of": monday.isoformat()},
        ),
    )
    await set_tenant_setting(tenant_id, LAST_SENT_SETTING, monday.isoformat())
    return {"sent": 1}


async def _build_report(tenant_id: UUID, today: date) -> dict:
    from app.db.models.appointment import Appointment
    from app.db.models.cobranzas import Charge
    from app.db.models.property import Property
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.session import async_session_factory

    week_ago = _utcnow() - timedelta(days=7)
    month0 = bs.month_start(today)

    async with async_session_factory() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        company = (tenant.company_name or tenant.display_name or "tu inmobiliaria") if tenant else "tu inmobiliaria"

        new_leads = (await s.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )).scalar() or 0

        visits_scheduled = (await s.execute(
            select(func.count(Appointment.id)).where(Appointment.created_at >= week_ago)
        )).scalar() or 0
        visits_done = (await s.execute(
            select(func.count(Appointment.id)).where(
                Appointment.status == "completed", Appointment.start_time >= week_ago
            )
        )).scalar() or 0
        no_shows = (await s.execute(
            select(func.count(Appointment.id)).where(
                Appointment.status == "no_show", Appointment.start_time >= week_ago
            )
        )).scalar() or 0

        top_rows = (await s.execute(
            select(Property.title, func.count(Appointment.id).label("c"))
            .join(Appointment, Appointment.property_id == Property.id)
            .where(Appointment.created_at >= week_ago)
            .group_by(Property.title)
            .order_by(func.count(Appointment.id).desc())
            .limit(3)
        )).all()

        # Cobranzas (mes en curso)
        paid_amount = (await s.execute(
            select(func.coalesce(func.sum(Charge.amount_paid), 0)).where(
                Charge.period == month0, Charge.status.in_(("paid", "partial"))
            )
        )).scalar() or 0
        pending_count = (await s.execute(
            select(func.count(Charge.id)).where(
                Charge.period == month0, Charge.status.in_(("pending", "partial"))
            )
        )).scalar() or 0
        overdue_count = (await s.execute(
            select(func.count(Charge.id)).where(
                Charge.status.in_(("pending", "partial")), Charge.due_date < today
            )
        )).scalar() or 0
        due_soon = (await s.execute(
            select(func.count(Charge.id)).where(
                Charge.status.in_(("pending", "partial")),
                Charge.due_date >= today,
                Charge.due_date <= today + timedelta(days=7),
            )
        )).scalar() or 0

    lines = [
        f"📊 Reporte semanal — {company}",
        "",
        f"🆕 Leads nuevos (7 días): {new_leads}",
        f"📅 Visitas agendadas: {visits_scheduled} · realizadas: {visits_done} · no-show: {no_shows}",
    ]
    if top_rows:
        lines.append("🏠 Top propiedades consultadas:")
        for i, (title, c) in enumerate(top_rows, 1):
            lines.append(f"   {i}. {title} ({c})")
    lines += [
        "",
        "💰 Cobranzas (mes en curso):",
        f"   Cobrado: {_money(paid_amount)}",
        f"   Por cobrar: {pending_count} · Vencidos: {overdue_count} · Por vencer (7d): {due_soon}",
    ]
    text = "\n".join(lines)
    summary_line = f"Leads {new_leads} · Visitas {visits_scheduled} · Vencidos {overdue_count}"
    return {"text": text, "summary_line": summary_line}


async def run() -> dict:
    summary: JobSummary = await for_each_tenant(JOB_NAME, _per_tenant)
    return summary.as_dict()
