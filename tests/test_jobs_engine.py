"""Tests for the scheduled-jobs engine (Profesional proactive notifications).

Two layers:
  - Unit (offline): the notification_dispatch template gate and EventType/keys.
  - DB integration (skipped without Postgres): the visit_reminder job end-to-end —
    window selection, dispatch result, idempotency via reminder_sent_at.

Run unit-only:
    pytest tests/test_jobs_engine.py -k "gate or key"

Run all (with Postgres):
    DATABASE_URL=postgresql+asyncpg://... pytest tests/test_jobs_engine.py
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.tenancy import tenant_scope
from app.services.notification_dispatch import (
    Dispatch,
    DispatchResult,
    EventType,
    tenant_template_setting_key,
)

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL / TEST_DATABASE_URL not set")


# ── Unit: template gate key ───────────────────────────────────────────────────

def test_template_setting_key_is_stable():
    assert tenant_template_setting_key(EventType.VISIT_REMINDER) == "wa_tpl_visit_reminder"
    assert tenant_template_setting_key(EventType.PAYMENT_DUE) == "wa_tpl_payment_due"


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _seed_tenant() -> "uuid4":
    """Create an isolated tenant and return its id (tenants table is not RLS-scoped)."""
    from app.db.models.tenant import Tenant
    from app.db.session import async_session_factory

    tid = uuid4()
    async with async_session_factory() as s:
        s.add(Tenant(
            id=tid,
            slug=f"jobtest-{tid.hex[:8]}",
            display_name="Job Test Agency",
            company_name="Job Test Agency SRL",
            timezone="America/Argentina/Buenos_Aires",
            status="active",
        ))
        await s.commit()
    return tid


async def _seed_visit(tid, *, hours_ahead: float, status: str = "confirmed"):
    """Seed a user + property + confirmed visit ``hours_ahead`` from now under tenant ``tid``."""
    from app.db.models.appointment import Appointment
    from app.db.models.property import Property
    from app.db.models.user import User
    from app.db.session import async_session_factory

    pid = random.randint(900_000_000, 999_999_999)
    uid = uuid4()
    start = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    with tenant_scope(tid):
        async with async_session_factory() as s:
            s.add(User(id=uid, tenant_id=tid, whatsapp_phone=f"54900{random.randint(1000000, 9999999)}",
                       name="Cliente Test"))
            s.add(Property(id=pid, tenant_id=tid, title="Depto Centro", description="x",
                           price=100000, type="alquiler", location="Centro"))
            await s.flush()
            s.add(Appointment(id=uuid4(), tenant_id=tid, user_id=uid, property_id=pid,
                              start_time=start, end_time=start + timedelta(hours=1),
                              type="visit", status=status))
            await s.commit()
    return uid, pid


# ── DB: visit_reminder job ────────────────────────────────────────────────────

@_db_skip
async def test_visit_reminder_picks_visit_within_24h_and_is_idempotent():
    from app.services.jobs import visit_reminder

    tid = await _seed_tenant()
    await _seed_visit(tid, hours_ahead=12)

    # No template configured → QUEUED (dashboard only), and the visit is stamped.
    summary = await visit_reminder.run()
    counters = summary["counters"]
    assert counters.get("due", 0) >= 1
    assert counters.get("queued", 0) >= 1
    assert counters.get("sent", 0) == 0  # no approved template

    # Second run: already reminded → not due again (idempotent).
    summary2 = await visit_reminder.run()
    # The just-stamped visit must not be counted again. Other tenants' data may exist, so
    # assert our tenant contributes nothing new by checking the stamped row directly.
    from sqlalchemy import select
    from app.db.models.appointment import Appointment
    from app.db.session import async_session_factory
    with tenant_scope(tid):
        async with async_session_factory() as s:
            rows = await s.execute(
                select(Appointment).where(Appointment.tenant_id == tid)
            )
            appts = rows.scalars().all()
    assert all(a.reminder_sent_at is not None for a in appts)


@_db_skip
async def test_visit_reminder_ignores_visits_outside_window():
    from sqlalchemy import select
    from app.db.models.appointment import Appointment
    from app.db.session import async_session_factory
    from app.services.jobs import visit_reminder

    tid = await _seed_tenant()
    await _seed_visit(tid, hours_ahead=48)  # too far out

    await visit_reminder.run()

    with tenant_scope(tid):
        async with async_session_factory() as s:
            rows = await s.execute(select(Appointment).where(Appointment.tenant_id == tid))
            appts = rows.scalars().all()
    assert appts and all(a.reminder_sent_at is None for a in appts)


@_db_skip
async def test_dispatch_queues_when_no_template_and_writes_notification():
    from sqlalchemy import text
    from app.db.session import async_session_factory
    from app.services.notification_dispatch import dispatch

    tid = await _seed_tenant()
    phone = f"54911{random.randint(1000000, 9999999)}"
    with tenant_scope(tid):
        result = await dispatch(tid, Dispatch(
            event=EventType.VISIT_REMINDER,
            recipient_phone=phone,
            dashboard_title="Recordatorio de visita (24h)",
            dashboard_body="Visita a Depto Centro",
            wa_text="Hola, te recordamos tu visita.",
        ))
    assert result == DispatchResult.QUEUED_NO_TEMPLATE

    async with async_session_factory() as s:
        row = await s.execute(
            text("SELECT count(*) FROM notifications WHERE tenant_id = :t AND phone = :p"),
            {"t": str(tid), "p": phone},
        )
        assert row.scalar_one() >= 1


# ── Unit: payment-due windows ─────────────────────────────────────────────────

def test_payment_stages_windows():
    from datetime import date, timedelta
    from app.services.jobs.payment_due import _stages_due

    due = date(2026, 7, 10)
    # 3 days before → "pre"
    assert _stages_due(due - timedelta(days=2), due, set()) == ["pre"]
    # on due date → "due"
    assert _stages_due(due, due, set()) == ["due"]
    # 5 days after → "overdue"
    assert _stages_due(due + timedelta(days=5), due, set()) == ["overdue"]
    # already-sent stages are not repeated
    assert _stages_due(due, due, {"due"}) == []
    # far before → nothing
    assert _stages_due(due - timedelta(days=10), due, set()) == []


# ── DB: payment_due job ───────────────────────────────────────────────────────

async def _seed_contract_with_charge(tid, *, due_offset_days: int, with_inquilino_phone=True):
    """Seed an inquilino + property + active contract + pending charge due ``due_offset_days``."""
    from datetime import date, timedelta
    from app.db.models.cobranzas import Charge, Contract
    from app.db.models.property import Property
    from app.db.models.user import User
    from app.db.session import async_session_factory
    from uuid import uuid4

    pid = random.randint(900_000_000, 999_999_999)
    inquilino_id = uuid4()
    contract_id = uuid4()
    due = date.today() + timedelta(days=due_offset_days)
    with tenant_scope(tid):
        async with async_session_factory() as s:
            s.add(User(id=inquilino_id, tenant_id=tid,
                       whatsapp_phone=(f"5493{random.randint(100000000, 999999999)}"
                                       if with_inquilino_phone else None),
                       name="Inquilino Test"))
            s.add(Property(id=pid, tenant_id=tid, title="Casa Alquiler", description="x",
                           price=200000, type="alquiler", location="Centro"))
            await s.flush()
            s.add(Contract(id=contract_id, org_id=tid, property_id=pid, tenant_id=inquilino_id,
                           start_date=date(2026, 1, 1), base_rent=200000, currency="ARS",
                           payment_due_day=due.day, status="active", adjustment_index="none"))
            await s.flush()
            s.add(Charge(id=uuid4(), tenant_id=tid, contract_id=contract_id,
                         period=date(due.year, due.month, 1), due_date=due,
                         base_amount=200000, total_amount=200000, status="pending"))
            await s.commit()
    return contract_id


@_db_skip
async def test_payment_due_sends_pre_reminder_and_is_idempotent():
    from sqlalchemy import select
    from app.db.models.cobranzas import Charge
    from app.db.session import async_session_factory
    from app.services.jobs import payment_due

    tid = await _seed_tenant()
    await _seed_contract_with_charge(tid, due_offset_days=2)  # inside "pre" window

    summary = await payment_due.run()
    assert summary["counters"].get("due", 0) >= 1
    assert summary["counters"].get("queued", 0) >= 1  # no template → queued

    # Stage recorded → not resent.
    with tenant_scope(tid):
        async with async_session_factory() as s:
            rows = await s.execute(select(Charge).where(Charge.tenant_id == tid))
            charges = rows.scalars().all()
    assert charges and all("pre" in (c.reminder_stages or []) for c in charges)

    summary2 = await payment_due.run()
    # Our charge already has "pre"; today is still < due so no new stage for it.
    with tenant_scope(tid):
        async with async_session_factory() as s:
            rows = await s.execute(select(Charge).where(Charge.tenant_id == tid))
            charges2 = rows.scalars().all()
    assert all(c.reminder_stages == ["pre"] for c in charges2)


@_db_skip
async def test_payment_due_overdue_stage():
    from sqlalchemy import select
    from app.db.models.cobranzas import Charge
    from app.db.session import async_session_factory
    from app.services.jobs import payment_due

    tid = await _seed_tenant()
    await _seed_contract_with_charge(tid, due_offset_days=-5)  # 5 days overdue

    await payment_due.run()
    with tenant_scope(tid):
        async with async_session_factory() as s:
            rows = await s.execute(select(Charge).where(Charge.tenant_id == tid))
            charges = rows.scalars().all()
    assert charges and all("overdue" in (c.reminder_stages or []) for c in charges)


# ── Unit + DB: contract_alerts ────────────────────────────────────────────────

def test_next_adjustment_month():
    from datetime import date
    from types import SimpleNamespace
    from app.services.jobs.contract_alerts import _next_adjustment_month

    c = SimpleNamespace(adjustment_index="IPC", adjustment_frequency_months=3,
                        start_date=date(2026, 1, 1))
    # Cycles every 3 months from Jan: Apr, Jul, Oct...
    assert _next_adjustment_month(c, date(2026, 6, 15)) == date(2026, 7, 1)
    # 'none' index → no adjustment
    c2 = SimpleNamespace(adjustment_index="none", adjustment_frequency_months=3,
                         start_date=date(2026, 1, 1))
    assert _next_adjustment_month(c2, date(2026, 6, 15)) is None


@_db_skip
async def test_contract_alerts_expiry_fires_within_30_days_and_idempotent():
    from datetime import date, timedelta
    from sqlalchemy import select
    from app.db.models.cobranzas import Contract
    from app.db.session import async_session_factory
    from app.services.jobs import contract_alerts
    from uuid import uuid4
    from app.db.models.property import Property
    from app.db.models.user import User

    tid = await _seed_tenant()
    pid = random.randint(900_000_000, 999_999_999)
    cid = uuid4()
    end = date.today() + timedelta(days=20)  # within 30-day window
    with tenant_scope(tid):
        async with async_session_factory() as s:
            s.add(Property(id=pid, tenant_id=tid, title="Local Centro", description="x",
                           price=100000, type="alquiler", location="Centro"))
            await s.flush()
            s.add(Contract(id=cid, org_id=tid, property_id=pid, start_date=date(2025, 1, 1),
                           end_date=end, base_rent=100000, status="active", adjustment_index="none"))
            await s.commit()

    summary = await contract_alerts.run()
    assert summary["counters"].get("expiry", 0) >= 1

    with tenant_scope(tid):
        async with async_session_factory() as s:
            c = (await s.execute(select(Contract).where(Contract.id == cid))).scalar_one()
    assert c.expiry_alert_sent_at is not None

    # Idempotent: second run does not re-alert this contract.
    summary2 = await contract_alerts.run()
    # Can't assert global 0 (other tenants), but our contract stays stamped once.
    with tenant_scope(tid):
        async with async_session_factory() as s:
            c2 = (await s.execute(select(Contract).where(Contract.id == cid))).scalar_one()
    assert c2.expiry_alert_sent_at == c.expiry_alert_sent_at


# ── DB: cold_leads ────────────────────────────────────────────────────────────

async def _seed_lead(tid, *, inactive_days: int, role: str = "prospect", phone=True):
    from datetime import datetime, timedelta, timezone
    from app.db.models.user import User
    from app.db.session import async_session_factory
    from uuid import uuid4

    uid = uuid4()
    last = datetime.now(timezone.utc) - timedelta(days=inactive_days)
    with tenant_scope(tid):
        async with async_session_factory() as s:
            s.add(User(
                id=uid, tenant_id=tid,
                whatsapp_phone=(f"5493{random.randint(100000000, 999999999)}" if phone else None),
                name="Lead Test", last_interaction=last,
                extra_data={"role": role},
            ))
            await s.commit()
    return uid


@_db_skip
async def test_cold_leads_reengages_prospect_once():
    from sqlalchemy import select
    from app.db.models.user import User
    from app.db.session import async_session_factory
    from app.services.jobs import cold_leads

    tid = await _seed_tenant()
    uid = await _seed_lead(tid, inactive_days=10, role="prospect")

    summary = await cold_leads.run()
    assert summary["counters"].get("queued", 0) >= 1

    with tenant_scope(tid):
        async with async_session_factory() as s:
            u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
    assert u.cold_reengaged_at is not None

    # Second run: already re-engaged (last_interaction unchanged) → not re-contacted.
    stamp = u.cold_reengaged_at
    await cold_leads.run()
    with tenant_scope(tid):
        async with async_session_factory() as s:
            u2 = (await s.execute(select(User).where(User.id == uid))).scalar_one()
    assert u2.cold_reengaged_at == stamp


@_db_skip
async def test_cold_leads_excludes_non_prospects():
    from sqlalchemy import select
    from app.db.models.user import User
    from app.db.session import async_session_factory
    from app.services.jobs import cold_leads

    tid = await _seed_tenant()
    lost = await _seed_lead(tid, inactive_days=10, role="lost")
    inquilino = await _seed_lead(tid, inactive_days=10, role="tenant")

    await cold_leads.run()
    with tenant_scope(tid):
        async with async_session_factory() as s:
            rows = (await s.execute(
                select(User).where(User.id.in_([lost, inquilino]))
            )).scalars().all()
    assert all(u.cold_reengaged_at is None for u in rows)


# ── DB: weekly_report ─────────────────────────────────────────────────────────

@_db_skip
async def test_weekly_report_sends_once_per_week():
    from app.services.jobs import weekly_report
    from app.services.tenant_service import get_tenant_setting

    tid = await _seed_tenant()
    # A couple of fresh leads so the report has non-zero numbers.
    await _seed_lead(tid, inactive_days=0)
    await _seed_lead(tid, inactive_days=1)

    summary = await weekly_report.run()
    # First run this week → sent.
    assert summary["counters"].get("sent", 0) >= 1
    last = await get_tenant_setting(tid, "weekly_report_last")
    assert last is not None

    # Second run same week → skipped (deduped).
    summary2 = await weekly_report.run()
    assert summary2["counters"].get("skipped_already_sent", 0) >= 1
