"""Job: payment-due reminders to the inquilino (Profesional 🔜 — cobranzas).

Three idempotent stages per pending charge, tracked in ``charges.reminder_stages``:
  - ``pre``     : PRE_DAYS before the due date ("se viene el vencimiento").
  - ``due``     : on the due date.
  - ``overdue`` : OVERDUE_DAYS after the due date if still unpaid (includes punitorios).

Reuses the existing pure billing helpers (``live_charge_figures`` / ``build_reminder_message``)
so the automated text matches the manual "Recordar" button in the cobranzas panel. Runs
daily; windows are non-overlapping so each run sends at most the single currently-relevant
stage, and a long sleep simply skips to the most relevant stage (catch-up safe).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import app.services.billing_service as bs
from app.services.jobs.base import JobSummary, for_each_tenant
from app.services.notification_dispatch import Dispatch, DispatchResult, EventType

JOB_NAME = "payment_due"
PRE_DAYS = 3
OVERDUE_DAYS = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stages_due(today, due, already: set[str]) -> list[str]:
    """Which reminder stages should fire today for a still-pending charge."""
    out: list[str] = []
    if "pre" not in already and (due - timedelta(days=PRE_DAYS)) <= today < due:
        out.append("pre")
    if "due" not in already and due <= today < (due + timedelta(days=OVERDUE_DAYS)):
        out.append("due")
    if "overdue" not in already and today >= (due + timedelta(days=OVERDUE_DAYS)):
        out.append("overdue")
    return out


async def _per_tenant(tenant_id: UUID) -> dict:
    from app.db.models.cobranzas import Charge, Contract
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.session import async_session_factory

    today = bs.today_ar()
    counters = {"due": 0, "sent": 0, "queued": 0, "skipped": 0, "failed": 0}

    async with async_session_factory() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        company = (tenant.company_name or tenant.display_name or "").strip() if tenant else ""

        rows = await session.execute(
            select(Charge)
            .options(selectinload(Charge.contract).selectinload(Contract.expenses))
            .where(Charge.status.in_(("pending", "partial")))
        )
        charges = rows.scalars().all()

        for ch in charges:
            contract = ch.contract
            if contract is None or ch.due_date is None:
                continue
            already = set(ch.reminder_stages or [])
            stages = _stages_due(today, ch.due_date, already)
            if not stages:
                continue

            inquilino = None
            if contract.tenant_id:
                inquilino = (await session.execute(
                    select(User).where(User.id == contract.tenant_id)
                )).scalar_one_or_none()
            phone = (inquilino.whatsapp_phone or inquilino.bsuid) if inquilino else None

            exp = bs.expenses_for_period(list(contract.expenses or []), ch.period)
            figures = bs.live_charge_figures(ch, contract, exp, today)
            message = bs.build_reminder_message(
                contract, ch, figures, company_name=company,
                tenant_name=(inquilino.name or "") if inquilino else "",
                currency=contract.currency or "ARS",
            )

            for stage in stages:
                counters["due"] += 1
                result = await _dispatch(tenant_id, ch, stage, phone, message, figures)
                _bump(counters, result)
                if result != DispatchResult.FAILED:
                    already.add(stage)

            ch.reminder_stages = sorted(already)
            ch.reminder_sent_at = _utcnow()

        await session.commit()

    return counters


def _bump(counters: dict, result: DispatchResult) -> None:
    if result == DispatchResult.SENT:
        counters["sent"] += 1
    elif result == DispatchResult.QUEUED_NO_TEMPLATE:
        counters["queued"] += 1
    elif result == DispatchResult.FAILED:
        counters["failed"] += 1
    else:
        counters["skipped"] += 1


async def _dispatch(tenant_id, charge, stage, phone, message, figures) -> DispatchResult:
    from app.services.notification_dispatch import dispatch

    titles = {
        "pre": "Pago próximo a vencer",
        "due": "Pago vence hoy",
        "overdue": "Pago vencido (mora)",
    }
    return await dispatch(
        tenant_id,
        Dispatch(
            event=EventType.PAYMENT_DUE,
            recipient_phone=phone,
            dashboard_title=titles.get(stage, "Recordatorio de pago"),
            dashboard_body=message.split("\n")[0],
            wa_text=message,
            dashboard_type="payment_due",
            metadata={"charge_id": str(charge.id), "stage": stage,
                      "total": figures.get("total_amount", 0)},
        ),
    )


async def run() -> dict:
    summary: JobSummary = await for_each_tenant(JOB_NAME, _per_tenant)
    return summary.as_dict()
