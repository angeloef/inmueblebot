"""Importación asistida de propiedades (plan 15).

- ``POST /admin/property-imports`` (auth normal): el cliente crea un pedido con
  archivos adjuntos (base64) + nota. El tenant/email se toman del account.
- ``GET /admin/property-imports`` (auth normal): lista **los del propio tenant**.
- ``GET /admin/property-imports/all`` (require_superadmin): lista cross-tenant.
- ``PATCH /admin/property-imports/{id}`` (require_superadmin): cambia estado/notas.
  Al pasar a ``completed`` envía email de aviso al requester.

Espeja el patrón de ``error_reports``.
"""

from __future__ import annotations

import base64
import uuid as _uuid
from datetime import datetime, timezone

UTC = timezone.utc

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import get_current_account, require_superadmin
from app.db.models import TenantAccount
from app.db.models.property_import_request import (
    ALLOWED_CONTENT_TYPES,
    IMPORT_STATUSES,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_REQUEST,
    PropertyImportFile,
    PropertyImportRequest,
)
from app.db.session import async_session_factory
from app.services import email_service

router = APIRouter(prefix="/admin/property-imports", tags=["property-imports"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


# ── Schemas ──────────────────────────────────────────────────────────────────


class ImportFileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    data: str = Field(min_length=1, description="Contenido base64 del archivo")


class PropertyImportCreate(BaseModel):
    note: str | None = Field(default=None, max_length=4000)
    item_count_estimate: int | None = Field(default=None, ge=1, le=10000)
    files: list[ImportFileIn] = Field(default_factory=list)


class PropertyImportUpdate(BaseModel):
    status: str | None = Field(default=None)
    admin_notes: str | None = Field(default=None, max_length=4000)
    item_count_estimate: int | None = Field(default=None, ge=1, le=10000)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _validate_file(f: ImportFileIn) -> None:
    if f.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de archivo no permitido: {f.content_type}",
        )
    try:
        raw = base64.b64decode(f.data, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Archivo con base64 inválido") from exc
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"El archivo {f.filename!r} supera el límite de 5 MB",
        )


def _file_to_dict(f: PropertyImportFile) -> dict:
    return {
        "id": str(f.id),
        "filename": f.filename,
        "content_type": f.content_type,
        "size_bytes": f.size_bytes,
        "created_at": f.created_at.isoformat() if isinstance(f.created_at, datetime) else None,
    }


def _to_dict(r: PropertyImportRequest, tenant_names: dict | None = None) -> dict:
    tid = str(r.tenant_id) if r.tenant_id else None
    return {
        "id": str(r.id),
        "tenant_id": tid,
        "tenant_name": (tenant_names or {}).get(tid) if tid else None,
        "account_id": str(r.account_id) if r.account_id else None,
        "requester_email": r.requester_email,
        "note": r.note,
        "status": r.status,
        "item_count_estimate": r.item_count_estimate,
        "admin_notes": r.admin_notes,
        "files": [_file_to_dict(f) for f in (r.files or [])],
        "file_count": len(r.files or []),
        "created_at": r.created_at.isoformat() if isinstance(r.created_at, datetime) else None,
        "updated_at": r.updated_at.isoformat() if isinstance(r.updated_at, datetime) else None,
        "completed_at": (
            r.completed_at.isoformat() if isinstance(r.completed_at, datetime) else None
        ),
    }


async def _tenant_name_map(db) -> dict[str, str]:  # noqa: ANN001
    from app.db.models.tenant import Tenant

    rows = (await db.execute(select(Tenant))).scalars().all()
    return {
        str(t.id): (t.display_name or t.company_name or t.slug or str(t.id))
        for t in rows
    }


# ── POST: crear pedido (auth normal) ─────────────────────────────────────────


@router.post("", status_code=201)
async def create_property_import(
    payload: PropertyImportCreate,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict:
    """El cliente sube archivos + nota. tenant/email vienen del account autenticado."""
    if len(payload.files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=422,
            detail=f"Se permiten máximo {MAX_FILES_PER_REQUEST} archivos por pedido",
        )
    for f in payload.files:
        _validate_file(f)

    request = PropertyImportRequest(
        tenant_id=account.tenant_id,
        account_id=account.id,
        requester_email=account.email,
        note=payload.note,
        item_count_estimate=payload.item_count_estimate,
        status="received",
    )
    async with async_session_factory() as db:
        db.add(request)
        await db.flush()
        for f in payload.files:
            raw = base64.b64decode(f.data)
            pf = PropertyImportFile(
                import_request_id=request.id,
                filename=f.filename,
                content_type=f.content_type,
                size_bytes=len(raw),
                data=f.data,
            )
            db.add(pf)
        await db.commit()
        await db.refresh(request)
        result = _to_dict(request)
    return result


# ── GET propio tenant (auth normal) ──────────────────────────────────────────


@router.get("/mine")
async def list_my_property_imports(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict:
    """Lista los pedidos del propio tenant (para el panel de estado del cliente)."""
    async with async_session_factory() as db:
        from sqlalchemy.orm import selectinload

        rows_with_files = (
            await db.execute(
                select(PropertyImportRequest)
                .options(selectinload(PropertyImportRequest.files))
                .where(PropertyImportRequest.tenant_id == account.tenant_id)
                .order_by(PropertyImportRequest.created_at.desc())
            )
        ).scalars().all()
        items = [_to_dict(r) for r in rows_with_files]
    return {"items": items, "total": len(items)}


# ── GET all (super-admin) ─────────────────────────────────────────────────────


@router.get("/all")
async def list_all_property_imports(
    status: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: object = Depends(require_superadmin),
) -> dict:
    from sqlalchemy.orm import selectinload

    offset = (page - 1) * page_size
    async with async_session_factory() as db:
        stmt = select(PropertyImportRequest).options(
            selectinload(PropertyImportRequest.files)
        )
        count_stmt = select(func.count()).select_from(PropertyImportRequest)

        if status in IMPORT_STATUSES:
            stmt = stmt.where(PropertyImportRequest.status == status)
            count_stmt = count_stmt.where(PropertyImportRequest.status == status)
        if tenant_id:
            try:
                tid = _uuid.UUID(tenant_id)
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=422, detail="Invalid tenant id") from exc
            stmt = stmt.where(PropertyImportRequest.tenant_id == tid)
            count_stmt = count_stmt.where(PropertyImportRequest.tenant_id == tid)

        total = (await db.execute(count_stmt)).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(PropertyImportRequest.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars().all()

        received_total = (
            await db.execute(
                select(func.count())
                .select_from(PropertyImportRequest)
                .where(PropertyImportRequest.status == "received")
            )
        ).scalar_one()

        tenant_names = await _tenant_name_map(db)
        items = [_to_dict(r, tenant_names) for r in rows]

    return {
        "items": items,
        "total": total,
        "received_total": received_total,
        "page": page,
        "page_size": page_size,
    }


# ── PATCH: gestión superadmin ─────────────────────────────────────────────────


@router.patch("/{request_id}")
async def update_property_import(
    request_id: str,
    payload: PropertyImportUpdate,
    _: object = Depends(require_superadmin),
) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") is not None and updates["status"] not in IMPORT_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        rid = _uuid.UUID(request_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid request id") from exc

    from sqlalchemy.orm import selectinload

    async with async_session_factory() as db:
        req = (
            await db.execute(
                select(PropertyImportRequest)
                .options(selectinload(PropertyImportRequest.files))
                .where(PropertyImportRequest.id == rid)
            )
        ).scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=404, detail="Import request not found")

        was_completed = req.status == "completed"
        for key, value in updates.items():
            setattr(req, key, value)

        if req.status == "completed" and not was_completed:
            req.completed_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(req)
        result = _to_dict(req)
        requester_email = req.requester_email

    # Email de aviso fuera de la transacción
    if req.status == "completed" and not was_completed:
        await email_service._send(
            to=requester_email,
            subject="¡Tus propiedades ya están cargadas!",
            html=(
                "<p>¡Hola! Te avisamos que tus propiedades ya fueron procesadas y cargadas "
                "en tu cuenta de InmuebleBot.</p>"
                "<p>Ya podés verlas en la sección <strong>Propiedades</strong> de tu dashboard.</p>"
                "<p>Gracias por confiar en nosotros.</p>"
            ),
        )

    return result


# ── GET archivo (descarga, superadmin) ────────────────────────────────────────


@router.get("/{request_id}/files/{file_id}")
async def download_import_file(
    request_id: str,
    file_id: str,
    _: object = Depends(require_superadmin),
) -> dict:
    """Devuelve el archivo en base64 para descarga en el front superadmin."""
    try:
        rid = _uuid.UUID(request_id)
        fid = _uuid.UUID(file_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid id") from exc

    async with async_session_factory() as db:
        f = (
            await db.execute(
                select(PropertyImportFile).where(
                    PropertyImportFile.id == fid,
                    PropertyImportFile.import_request_id == rid,
                )
            )
        ).scalar_one_or_none()
        if not f:
            raise HTTPException(status_code=404, detail="File not found")
        return {
            "id": str(f.id),
            "filename": f.filename,
            "content_type": f.content_type,
            "size_bytes": f.size_bytes,
            "data": f.data,
        }
