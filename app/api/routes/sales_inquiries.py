"""Consultas Enterprise 'Hablar con ventas' (plan 20).

- POST /sales-inquiries  (auth normal): persiste la consulta y avisa por email.
- GET  /sales-inquiries  (super-admin): lista todas las consultas.
- PATCH /sales-inquiries/{id} (super-admin): actualiza status.

Tabla global (sin RLS), igual que error_reports.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import get_current_account, require_superadmin
from app.db.models import SalesInquiry, TenantAccount
from app.db.session import async_session_factory
from app.services.email_service import send_sales_inquiry_notification

router = APIRouter(prefix="/sales-inquiries", tags=["sales-inquiries"])

_SALES_EMAIL = "ventas@viviendapp.com"
STATUSES = ("open", "contacted", "closed")
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class SalesInquiryCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    property_count: str | None = Field(default=None, max_length=50)
    message: str | None = Field(default=None, max_length=2000)


class SalesInquiryUpdate(BaseModel):
    status: str | None = None


def _to_dict(r: SalesInquiry, tenant_names: dict | None = None) -> dict:
    tid = str(r.tenant_id) if r.tenant_id else None
    return {
        "id": str(r.id),
        "tenant_id": tid,
        "tenant_name": (tenant_names or {}).get(tid) if tid else None,
        "contact_name": r.contact_name,
        "contact_email": r.contact_email,
        "phone": r.phone,
        "property_count": r.property_count,
        "message": r.message,
        "status": r.status,
        "created_at": r.created_at.isoformat() if isinstance(r.created_at, datetime) else None,
    }


async def _tenant_name_map(db) -> dict[str, str]:  # noqa: ANN001
    from app.db.models.tenant import Tenant

    rows = (await db.execute(select(Tenant))).scalars().all()
    return {
        str(t.id): (t.display_name or t.company_name or t.slug or str(t.id))
        for t in rows
    }


@router.post("", status_code=201)
async def create_sales_inquiry(
    payload: SalesInquiryCreate,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict:
    """Crea la consulta y avisa a ventas por email."""
    inquiry = SalesInquiry(
        tenant_id=account.tenant_id,
        account_id=account.id,
        contact_name=payload.contact_name.strip(),
        contact_email=account.email,
        phone=payload.phone,
        property_count=payload.property_count,
        message=payload.message,
        status="open",
    )
    async with async_session_factory() as db:
        db.add(inquiry)
        await db.commit()
        await db.refresh(inquiry)
        result = _to_dict(inquiry)

    # resolve tenant name for email (best-effort, non-blocking)
    try:
        async with async_session_factory() as db:
            name_map = await _tenant_name_map(db)
        tenant_name = name_map.get(result["tenant_id"], result["tenant_id"] or "—")
    except Exception:
        tenant_name = "—"

    await send_sales_inquiry_notification(
        to=_SALES_EMAIL,
        contact_name=payload.contact_name.strip(),
        contact_email=account.email or "—",
        tenant_name=tenant_name,
        phone=payload.phone,
        property_count=payload.property_count,
        message=payload.message,
    )

    return result


@router.get("")
async def list_sales_inquiries(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: object = Depends(require_superadmin),
) -> dict:
    offset = (page - 1) * page_size
    async with async_session_factory() as db:
        stmt = select(SalesInquiry)
        count_stmt = select(func.count()).select_from(SalesInquiry)
        if status in STATUSES:
            stmt = stmt.where(SalesInquiry.status == status)
            count_stmt = count_stmt.where(SalesInquiry.status == status)
        total = (await db.execute(count_stmt)).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(SalesInquiry.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()
        open_total = (
            await db.execute(
                select(func.count())
                .select_from(SalesInquiry)
                .where(SalesInquiry.status == "open")
            )
        ).scalar_one()
        tenant_names = await _tenant_name_map(db)
        items = [_to_dict(r, tenant_names) for r in rows]
    return {
        "items": items, "total": total, "open_total": open_total,
        "page": page, "page_size": page_size,
    }


@router.patch("/{inquiry_id}")
async def update_sales_inquiry(
    inquiry_id: str,
    payload: SalesInquiryUpdate,
    _: object = Depends(require_superadmin),
) -> dict:
    if payload.status is not None and payload.status not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    try:
        iid = _uuid.UUID(inquiry_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid inquiry id") from exc

    async with async_session_factory() as db:
        inquiry = (
            await db.execute(select(SalesInquiry).where(SalesInquiry.id == iid))
        ).scalar_one_or_none()
        if not inquiry:
            raise HTTPException(status_code=404, detail="Sales inquiry not found")
        if payload.status:
            inquiry.status = payload.status
        await db.commit()
        await db.refresh(inquiry)
        result = _to_dict(inquiry)
    return result
