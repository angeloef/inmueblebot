"""Job: cold-lead re-engagement (Profesional 🔜).

Re-engages prospects with no activity for COLD_AFTER_DAYS. One-shot per cooling period
(``users.cold_reengaged_at``): a lead is contacted once; if they reply (last_interaction
advances past the marker) and go cold again, they become eligible once more.

Exclusions (per product decision):
  - not a prospect (role lost/tenant/owner in extra_data) — closed/converted/owner.
  - has an active rental contract (already an inquilino).
  - has a future confirmed visit (not actually cold).
  - conversation is handed off to a human (``conversations.bot_paused``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.services.jobs.base import JobSummary, for_each_tenant
from app.services.notification_dispatch import Dispatch, DispatchResult, EventType

JOB_NAME = "cold_leads"
COLD_AFTER_DAYS = 7
_PROSPECT_ROLES = {"prospect", ""}  # missing role is treated as a prospect


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _role_of(extra_raw) -> str:
    if isinstance(extra_raw, dict):
        return (extra_raw.get("role") or "").lower()
    if isinstance(extra_raw, str):
        try:
            d = json.loads(extra_raw)
            return (d.get("role") or "").lower() if isinstance(d, dict) else ""
        except Exception:
            return ""
    return ""


def _build_message(user, company: str) -> str:
    name = f" {user.name}" if user.name else ""
    prefs = []
    if user.property_type:
        prefs.append("/".join(user.property_type))
    if user.location_preferences:
        prefs.append("en " + "/".join(user.location_preferences))
    what = (" " + " ".join(prefs)) if prefs else ""
    firma = f"\n\n{company}" if company else ""
    return (
        f"Hola{name}, ¿seguís buscando{what}? Sumamos propiedades nuevas y me encantaría "
        f"mostrarte las que mejor encajan. ¿Querés que te pase algunas opciones?" + firma
    )


async def _per_tenant(tenant_id: UUID) -> dict:
    from app.db.models.appointment import Appointment
    from app.db.models.cobranzas import Contract
    from app.db.models.conversation import Conversation
    from app.db.models.tenant import Tenant
    from app.db.models.user import User
    from app.db.session import async_session_factory

    now = _utcnow()
    cutoff = now - timedelta(days=COLD_AFTER_DAYS)
    counters = {"candidates": 0, "reengaged": 0, "queued": 0, "excluded": 0, "skipped": 0, "failed": 0}

    async with async_session_factory() as session:
        tenant = (await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        company = (tenant.company_name or tenant.display_name or "").strip() if tenant else ""

        candidates = (await session.execute(
            select(User).where(
                User.last_interaction.is_not(None),
                User.last_interaction <= cutoff,
                User.whatsapp_phone.is_not(None),
            )
        )).scalars().all()
        counters["candidates"] = len(candidates)

        for user in candidates:
            # One-shot per cooling: skip if already re-engaged since they last interacted.
            if user.cold_reengaged_at is not None and user.cold_reengaged_at >= user.last_interaction:
                continue
            if _role_of(user.extra_data) not in _PROSPECT_ROLES:
                counters["excluded"] += 1
                continue
            if await _has_active_contract(session, Contract, user.id):
                counters["excluded"] += 1
                continue
            if await _has_future_visit(session, Appointment, user.id, now):
                counters["excluded"] += 1
                continue
            if await _is_handed_off(session, Conversation, user.id):
                counters["excluded"] += 1
                continue

            result = await _dispatch(tenant_id, user, _build_message(user, company))
            if result == DispatchResult.SENT:
                counters["reengaged"] += 1
            elif result == DispatchResult.QUEUED_NO_TEMPLATE:
                counters["queued"] += 1
            elif result == DispatchResult.FAILED:
                counters["failed"] += 1
            else:
                counters["skipped"] += 1

            if result != DispatchResult.FAILED:
                user.cold_reengaged_at = now

        await session.commit()

    return counters


async def _has_active_contract(session, Contract, user_id) -> bool:
    row = await session.execute(
        select(Contract.id).where(Contract.tenant_id == user_id, Contract.status == "active").limit(1)
    )
    return row.scalar_one_or_none() is not None


async def _has_future_visit(session, Appointment, user_id, now) -> bool:
    row = await session.execute(
        select(Appointment.id).where(
            Appointment.user_id == user_id,
            Appointment.status == "confirmed",
            Appointment.start_time > now,
        ).limit(1)
    )
    return row.scalar_one_or_none() is not None


async def _is_handed_off(session, Conversation, user_id) -> bool:
    row = await session.execute(
        select(Conversation.id).where(
            Conversation.user_id == user_id,
            Conversation.bot_paused.is_(True),
        ).limit(1)
    )
    return row.scalar_one_or_none() is not None


async def _dispatch(tenant_id, user, message) -> DispatchResult:
    from app.services.notification_dispatch import dispatch

    return await dispatch(
        tenant_id,
        Dispatch(
            event=EventType.COLD_LEAD,
            recipient_phone=user.whatsapp_phone or user.bsuid,
            dashboard_title="Lead frío — re-engagement",
            dashboard_body=f"{user.name or user.whatsapp_phone}: sin actividad hace +{COLD_AFTER_DAYS} días",
            wa_text=message,
            dashboard_type="cold_lead",
            metadata={"user_id": str(user.id)},
        ),
    )


async def run() -> dict:
    summary: JobSummary = await for_each_tenant(JOB_NAME, _per_tenant)
    return summary.as_dict()
