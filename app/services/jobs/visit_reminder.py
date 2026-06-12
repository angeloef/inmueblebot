"""Job: 24h-before visit reminder (Profesional 🔜 — reduce no-show).

Reminds the client by WhatsApp about an upcoming property visit. Runs hourly; for each
active tenant it picks confirmed visits starting within the next 24h that have not been
reminded yet, dispatches the reminder (template gate), and stamps ``reminder_sent_at`` for
idempotency. Safe to run repeatedly and to catch up after the web service wakes from sleep.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from loguru import logger
from sqlalchemy import select

from app.services.jobs.base import JobSummary, for_each_tenant
from app.services.notification_dispatch import Dispatch, DispatchResult, EventType

JOB_NAME = "visit_reminder"
_REMIND_WITHIN = timedelta(hours=24)

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _format_when(dt: datetime) -> str:
    return f"{dt.day} de {_MESES[dt.month - 1]} a las {dt.strftime('%H:%M')}"


async def _per_tenant(tenant_id: UUID) -> dict:
    from app.db.models.appointment import Appointment
    from app.db.models.property import Property
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.session import async_session_factory

    now = datetime.now(timezone.utc)
    horizon = now + _REMIND_WITHIN
    counters = {"due": 0, "sent": 0, "queued": 0, "skipped": 0, "failed": 0}

    async with async_session_factory() as session:
        rows = await session.execute(
            select(Appointment, User, Property, Tenant)
            .join(User, Appointment.user_id == User.id)
            .join(Property, Appointment.property_id == Property.id)
            .join(Tenant, Tenant.id == tenant_id)
            .where(
                Appointment.type == "visit",
                Appointment.status == "confirmed",
                Appointment.start_time > now,
                Appointment.start_time <= horizon,
                Appointment.reminder_sent_at.is_(None),
            )
        )
        pending = rows.all()
        counters["due"] = len(pending)

        for appt, user, prop, tenant in pending:
            phone = getattr(user, "whatsapp_phone", None)
            company = (tenant.company_name or tenant.display_name or "").strip()
            greeting = f"Hola {user.name}".strip() if user.name else "Hola"
            when = _format_when(appt.start_time)
            wa_text = (
                f"{greeting}, te recordamos tu visita a *{prop.title}* "
                f"({prop.location}) mañana {when}."
                + (f"\n\n{company}" if company else "")
            )
            result = await _dispatch_reminder(tenant_id, appt, prop, phone, wa_text, when)

            if result == DispatchResult.SENT:
                counters["sent"] += 1
            elif result == DispatchResult.QUEUED_NO_TEMPLATE:
                counters["queued"] += 1
            elif result == DispatchResult.FAILED:
                counters["failed"] += 1
            else:
                counters["skipped"] += 1

            # Stamp regardless of send/queue: the reminder has been actioned (either sent
            # or surfaced in the dashboard for manual follow-up). FAILED is left unstamped
            # so the next run retries it.
            if result != DispatchResult.FAILED:
                appt.reminder_sent_at = now

        await session.commit()

    return counters


async def _dispatch_reminder(tenant_id, appt, prop, phone, wa_text, when) -> DispatchResult:
    from app.services.notification_dispatch import dispatch

    return await dispatch(
        tenant_id,
        Dispatch(
            event=EventType.VISIT_REMINDER,
            recipient_phone=phone,
            dashboard_title="Recordatorio de visita (24h)",
            dashboard_body=f"Visita a {prop.title} — {when}",
            wa_text=wa_text,
            dashboard_type="visit_reminder",
            metadata={"appointment_id": str(appt.id), "property_id": prop.id},
        ),
    )


async def run() -> dict:
    summary: JobSummary = await for_each_tenant(JOB_NAME, _per_tenant)
    return summary.as_dict()
