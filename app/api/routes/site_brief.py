"""Site-brief intake API (Profesional 🔜 — "Mi sitio web", Fase A).

The inmobiliaria fills its website brief from the dashboard; the founder reads it and builds
the public site manually (no templates / auto-gen yet). One brief per tenant, RLS-scoped.

Auth: ``get_current_account`` (sets the tenant context). All access is implicitly scoped to
the logged-in agency's tenant.

Design presets (the form offers these; storage is free-form JSONB so it can evolve):
  - design.style_direction : moderno | clasico | minimalista | lujo
  - design.color_mood      : claro | oscuro | colorido | sobrio
plus free-text: design.references, design.avoid, design.notes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_account
from app.db.models import SiteBrief, TenantAccount
from app.db.session import async_session_factory

router = APIRouter(prefix="/site-brief", tags=["site-brief"])

_SECTIONS = ("brand", "pitch", "contact", "domain", "design", "catalog")


class SiteBriefUpdate(BaseModel):
    """Partial update — any subset of sections plus optional status."""

    brand: Optional[dict] = None
    pitch: Optional[dict] = None
    contact: Optional[dict] = None
    domain: Optional[dict] = None
    design: Optional[dict] = None
    catalog: Optional[dict] = None
    status: Optional[str] = None


def _serialize(brief: SiteBrief | None, tenant_id) -> dict:
    if brief is None:
        return {
            "tenant_id": str(tenant_id),
            "status": "draft",
            **{s: None for s in _SECTIONS},
            "submitted_at": None,
            "updated_at": None,
        }
    return {
        "tenant_id": str(brief.tenant_id),
        "status": brief.status,
        "brand": brief.brand,
        "pitch": brief.pitch,
        "contact": brief.contact,
        "domain": brief.domain,
        "design": brief.design,
        "catalog": brief.catalog,
        "submitted_at": brief.submitted_at.isoformat() if brief.submitted_at else None,
        "updated_at": brief.updated_at.isoformat() if brief.updated_at else None,
    }


async def _get_brief(session, tenant_id) -> SiteBrief | None:
    row = await session.execute(select(SiteBrief).where(SiteBrief.tenant_id == tenant_id))
    return row.scalar_one_or_none()


@router.get("")
async def get_my_brief(account: TenantAccount = Depends(get_current_account)) -> dict:
    """Return the agency's site brief (or an empty draft shape if none exists yet)."""
    async with async_session_factory() as session:
        brief = await _get_brief(session, account.tenant_id)
        return _serialize(brief, account.tenant_id)


@router.put("")
async def update_my_brief(
    data: SiteBriefUpdate,
    account: TenantAccount = Depends(get_current_account),
) -> dict:
    """Upsert any subset of the brief sections for the agency's tenant."""
    updates = data.model_dump(exclude_unset=True)
    async with async_session_factory() as session:
        brief = await _get_brief(session, account.tenant_id)
        if brief is None:
            brief = SiteBrief(tenant_id=account.tenant_id, status="draft")
            session.add(brief)
        for key, value in updates.items():
            if key in _SECTIONS or key == "status":
                setattr(brief, key, value)
        await session.commit()
        await session.refresh(brief)
        return _serialize(brief, account.tenant_id)


@router.post("/submit")
async def submit_my_brief(account: TenantAccount = Depends(get_current_account)) -> dict:
    """Mark the brief as submitted and notify the founder (dashboard notification)."""
    async with async_session_factory() as session:
        brief = await _get_brief(session, account.tenant_id)
        if brief is None:
            brief = SiteBrief(tenant_id=account.tenant_id)
            session.add(brief)
        brief.status = "submitted"
        brief.submitted_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(brief)
        result = _serialize(brief, account.tenant_id)

    try:
        from app.services.notification_service import notification_service
        await notification_service.create(
            type="site_brief_submitted",
            title="Brief de sitio web enviado",
            body="Una inmobiliaria completó y envió su brief de sitio web.",
            metadata={"tenant_id": str(account.tenant_id)},
        )
    except Exception:
        pass

    return result
