"""Documentos adjuntos a clientes/contratos (Enterprise).

Carga manual desde el dashboard. El archivo viaja en base64 y se guarda en la tabla
``documents`` (RLS org-aware). Scoping por tenant efectivo (sucursal/consolidado) lo da
``resolve_tenant_id()`` + RLS, igual que el resto de /admin.
"""

from __future__ import annotations

import base64
import binascii
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import require_active_subscription
from app.core.tenancy import resolve_tenant_id
from app.db.models import TenantAccount
from app.db.models.document import DOCUMENT_CATEGORIES, Document
from app.db.session import async_session_factory

router = APIRouter(prefix="/documents", tags=["documents"])

# Límite de tamaño del archivo decodificado (base64 infla ~33% en la DB).
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


class DocumentCreate(BaseModel):
    client_id: str | None = None
    contract_id: str | None = None
    category: str = Field(min_length=1, max_length=30)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    data: str = Field(min_length=1, description="base64 (con o sin prefijo data URI)")
    note: str | None = Field(default=None, max_length=500)


class DocumentOut(BaseModel):
    id: str
    client_id: str | None
    contract_id: str | None
    category: str
    filename: str
    content_type: str
    size_bytes: int
    note: str | None
    uploaded_by: str | None
    created_at: str


def _to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=str(d.id),
        client_id=str(d.client_id) if d.client_id else None,
        contract_id=str(d.contract_id) if d.contract_id else None,
        category=d.category,
        filename=d.filename,
        content_type=d.content_type,
        size_bytes=d.size_bytes,
        note=d.note,
        uploaded_by=d.uploaded_by,
        created_at=str(d.created_at),
    )


def _strip_data_uri(b64: str) -> str:
    """Acepta 'data:<mime>;base64,XXXX' o 'XXXX' y devuelve solo el payload base64."""
    if b64.startswith("data:") and "," in b64:
        return b64.split(",", 1)[1]
    return b64


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    payload: DocumentCreate,
    account: TenantAccount = Depends(require_active_subscription),  # noqa: B008
) -> DocumentOut:
    if not payload.client_id and not payload.contract_id:
        raise HTTPException(status_code=422, detail="Indicá un cliente o un contrato")
    if payload.category not in DOCUMENT_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Categoría inválida. Opciones: {', '.join(DOCUMENT_CATEGORIES)}",
        )

    raw_b64 = _strip_data_uri(payload.data)
    try:
        decoded = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Archivo base64 inválido") from exc
    size = len(decoded)
    if size == 0:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    if size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el máximo de {MAX_FILE_BYTES // (1024 * 1024)} MB",
        )

    def _opt_uuid(v: str | None) -> UUID | None:
        if not v:
            return None
        try:
            return UUID(v)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="ID inválido") from exc

    doc = Document(
        tenant_id=resolve_tenant_id(),  # tenant efectivo (sucursal/consolidado) — RLS WITH CHECK
        client_id=_opt_uuid(payload.client_id),
        contract_id=_opt_uuid(payload.contract_id),
        category=payload.category,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=size,
        data=raw_b64,
        note=payload.note,
        uploaded_by=account.email,
    )
    async with async_session_factory() as s:
        s.add(doc)
        await s.commit()
        await s.refresh(doc)
    return _to_out(doc)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    client_id: str | None = Query(default=None),
    contract_id: str | None = Query(default=None),
    _: TenantAccount = Depends(require_active_subscription),  # noqa: B008
) -> list[DocumentOut]:
    """Lista metadatos (sin el blob). Filtra por cliente y/o contrato; RLS scopea por tenant."""
    stmt = select(Document).order_by(Document.created_at.desc())
    if client_id:
        try:
            stmt = stmt.where(Document.client_id == UUID(client_id))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="client_id inválido") from exc
    if contract_id:
        try:
            stmt = stmt.where(Document.contract_id == UUID(contract_id))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="contract_id inválido") from exc

    async with async_session_factory() as s:
        rows = (await s.execute(stmt)).scalars().all()
    return [_to_out(d) for d in rows]


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: UUID,
    _: TenantAccount = Depends(require_active_subscription),  # noqa: B008
) -> Response:
    async with async_session_factory() as s:
        doc = await s.get(Document, doc_id)
    if doc is None:  # RLS hides other tenants' rows → get() returns None
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    try:
        content = base64.b64decode(doc.data, validate=False)
    except (binascii.Error, ValueError) as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Documento corrupto") from exc
    return Response(
        content=content,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: UUID,
    _: TenantAccount = Depends(require_active_subscription),  # noqa: B008
) -> dict:
    async with async_session_factory() as s:
        doc = await s.get(Document, doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        await s.delete(doc)
        await s.commit()
    return {"status": "deleted", "id": str(doc_id)}
