"""Job: contract-expiry + IPC-adjustment alerts to the agency (Profesional 🔜 — cobranzas).

Operational heads-ups for the inmobiliaria (NOT the inquilino):
  - expiry : 30 days before a contract's end_date — "contrato por vencer".
  - ipc    : IPC_LEAD_DAYS before the next IPC adjustment cycle — "verificá el índice".

Both go to the dashboard and (per product decision) to the owner's WhatsApp when a number is
configured for the tenant (``owner_phone`` in tenant_settings); otherwise dashboard-only.
Idempotent via ``contracts.expiry_alert_sent_at`` and ``contracts.ipc_alert_for``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

import app.services.billing_service as bs
from app.services.jobs.base import JobSummary, for_each_tenant
from app.services.notification_dispatch import Dispatch, EventType

JOB_NAME = "contract_alerts"
EXPIRY_DAYS = 30
IPC_LEAD_DAYS = 7
OWNER_PHONE_SETTING = "owner_phone"

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(d) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _next_adjustment_month(contract, today):
    """First-of-month date of the next IPC adjustment after ``today``, or None."""
    mode = (contract.adjustment_index or "none")
    freq = contract.adjustment_frequency_months or 0
    if mode == "none" or mode == "fixed" or freq <= 0 or not contract.start_date:
        return None
    start_m = bs.month_start(contract.start_date)
    next_cycle = bs.adjustment_cycles_elapsed(contract, today) + 1
    return bs.add_months(start_m, next_cycle * freq)


async def _per_tenant(tenant_id: UUID) -> dict:
    from app.db.models.cobranzas import Contract
    from app.db.models.property import Property
    from app.db.models.user import User
    from app.db.session import async_session_factory
    from app.services.tenant_service import get_tenant_setting

    today = bs.today_ar()
    counters = {"expiry": 0, "ipc": 0, "queued": 0, "skipped": 0}
    owner_phone = await get_tenant_setting(tenant_id, OWNER_PHONE_SETTING)

    async with async_session_factory() as session:
        contracts = (await session.execute(
            select(Contract).where(Contract.status == "active")
        )).scalars().all()

        for c in contracts:
            label = await _contract_label(session, c, Property, User)

            # ── Expiry: 30 days before end_date ──
            if (
                c.expiry_alert_sent_at is None
                and c.end_date is not None
                and (c.end_date - timedelta(days=EXPIRY_DAYS)) <= today <= c.end_date
            ):
                body = f"El contrato de {label} vence el {_fmt(c.end_date)}."
                await _alert(tenant_id, EventType.CONTRACT_EXPIRY, owner_phone,
                            "Contrato por vencer", body, c)
                c.expiry_alert_sent_at = _utcnow()
                counters["expiry"] += 1

            # ── IPC: lead days before the next adjustment cycle ──
            next_adj = _next_adjustment_month(c, today)
            if (
                next_adj is not None
                and c.ipc_alert_for != next_adj
                and (next_adj - timedelta(days=IPC_LEAD_DAYS)) <= today <= next_adj
                and (c.end_date is None or next_adj <= c.end_date)
            ):
                body = (
                    f"El contrato de {label} ajusta por IPC en "
                    f"{_MESES[next_adj.month - 1]} {next_adj.year}. "
                    f"Verificá que el índice esté cargado."
                )
                await _alert(tenant_id, EventType.IPC_ADJUSTMENT, owner_phone,
                            "Próximo ajuste IPC", body, c)
                c.ipc_alert_for = next_adj
                counters["ipc"] += 1

        await session.commit()

    return counters


async def _contract_label(session, contract, Property, User) -> str:
    parts: list[str] = []
    if contract.property_id:
        title = (await session.execute(
            select(Property.title).where(Property.id == contract.property_id)
        )).scalar_one_or_none()
        if title:
            parts.append(title)
    if contract.tenant_id:
        name = (await session.execute(
            select(User.name).where(User.id == contract.tenant_id)
        )).scalar_one_or_none()
        if name:
            parts.append(f"inquilino {name}")
    return " — ".join(parts) if parts else "un contrato"


async def _alert(tenant_id, event, owner_phone, title, body, contract) -> None:
    from app.services.notification_dispatch import dispatch

    await dispatch(
        tenant_id,
        Dispatch(
            event=event,
            recipient_phone=owner_phone,
            dashboard_title=title,
            dashboard_body=body,
            wa_text=body,
            dashboard_type=event.value,
            metadata={"contract_id": str(contract.id)},
        ),
    )


async def run() -> dict:
    summary: JobSummary = await for_each_tenant(JOB_NAME, _per_tenant)
    return summary.as_dict()
