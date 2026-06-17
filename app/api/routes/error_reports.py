"""Reporte de errores in-app + triage super-admin (plan 07).

- ``POST /admin/error-reports`` (auth normal): cualquier usuario autenticado de una
  inmobiliaria envía un reporte. El ``context`` se **redacta** (se quitan credenciales)
  y se limita en tamaño antes de persistir. El ``tenant_id`` y el ``reporter_email`` se
  toman del account autenticado — el cliente no puede falsearlos.
- ``GET /admin/error-reports`` + ``PATCH /admin/error-reports/{id}`` (super-admin): los
  2 devs listan/filtran y hacen triage (status/severity/notas) cross-tenant. Gateado por
  ``require_superadmin`` (plan 04) ⇒ cualquier no-superadmin → 401/403.

``error_reports`` es una tabla global (sin RLS), como ``subscriptions``.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import get_current_account, require_superadmin
from app.db.models import ErrorReport, TenantAccount
from app.db.session import async_session_factory

router = APIRouter(prefix="/admin/error-reports", tags=["error-reports"])

# Topes defensivos: el body lo manda un cliente no-superadmin, así que acotamos todo.
MAX_MESSAGE_LEN = 4000
MAX_CONTEXT_BYTES = 8000
MAX_CONSOLE_TAIL = 20
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

SEVERITIES = ("low", "med", "high")
STATUSES = ("open", "in_progress", "resolved", "wont_fix")

# Claves cuyo valor jamás se persiste: credenciales / material sensible. Se comparan en
# minúsculas por substring, así "Authorization", "access_token", "X-Api-Key" caen todos.
# LIMITACIÓN conocida: la redacción es por NOMBRE de clave, no por contenido. Un secreto
# embebido como valor en una clave de nombre inocuo (p.ej. {"detail": "token eyJ..."}) no
# se detecta. Aceptable porque el context es estructurado (dict del cliente) y la lectura
# es solo super-admin; si en el futuro se capturara texto libre, redactar también valores.
_REDACT_KEYS = (
    "token",
    "cookie",
    "authorization",
    "auth",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "session",
    "bearer",
    "credential",
    "jwt",
    "x-api-key",
)
_REDACTED = "[redacted]"


def _should_redact(key: str) -> bool:
    low = key.lower()
    return any(marker in low for marker in _REDACT_KEYS)


def _redact(value: object, depth: int = 0) -> object:
    """Copia recursiva del context quitando credenciales. Acota profundidad/tamaño."""
    if depth > 5:
        return _REDACTED
    if isinstance(value, dict):
        return {
            k: (_REDACTED if _should_redact(str(k)) else _redact(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v, depth + 1) for v in value[:50]]
    if isinstance(value, str):
        return value[:2000]
    return value


def _sanitize_context(raw: object) -> dict:
    """Redacta, recorta console_tail y garantiza un dict acotado en tamaño."""
    if not isinstance(raw, dict):
        return {}
    # Recortar console_tail a las ÚLTIMAS líneas ANTES de redactar: _redact trunca listas
    # por la cabeza (primeras 50), pero del log de consola interesan las más recientes.
    pruned = dict(raw)
    if isinstance(pruned.get("console_tail"), list):
        pruned["console_tail"] = pruned["console_tail"][-MAX_CONSOLE_TAIL:]
    cleaned = _redact(pruned)
    if not isinstance(cleaned, dict):
        return {}
    # Salvaguarda final de tamaño: si aún excede, descartamos el console_tail.
    import json

    if len(json.dumps(cleaned, default=str)) > MAX_CONTEXT_BYTES:
        cleaned.pop("console_tail", None)
        cleaned["_truncated"] = True
    return cleaned if isinstance(cleaned, dict) else {}


# ── Schemas ──────────────────────────────────────────────────────────────────


class ErrorReportCreate(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LEN)
    severity: str = Field(default="med")
    context: dict = Field(default_factory=dict)


class ErrorReportTriage(BaseModel):
    status: str | None = Field(default=None)
    severity: str | None = Field(default=None)
    triage_notes: str | None = Field(default=None, max_length=4000)


async def _tenant_name_map(db) -> dict[str, str]:  # noqa: ANN001
    """id(str) → nombre legible de la inmobiliaria, para anotar cada reporte."""
    from app.db.models.tenant import Tenant

    rows = (await db.execute(select(Tenant))).scalars().all()
    return {
        str(t.id): (t.display_name or t.company_name or t.slug or str(t.id))
        for t in rows
    }


def _to_dict(r: ErrorReport, tenant_names: dict[str, str] | None = None) -> dict:
    tid = str(r.tenant_id) if r.tenant_id else None
    return {
        "id": str(r.id),
        "tenant_id": tid,
        "tenant_name": (tenant_names or {}).get(tid) if tid else None,
        "account_id": str(r.account_id) if r.account_id else None,
        "reporter_email": r.reporter_email,
        "message": r.message,
        "context": r.context or {},
        "severity": r.severity,
        "status": r.status,
        "triage_notes": r.triage_notes,
        "created_at": r.created_at.isoformat() if isinstance(r.created_at, datetime) else None,
        "updated_at": r.updated_at.isoformat() if isinstance(r.updated_at, datetime) else None,
    }


# ── POST: crear reporte (auth normal) ────────────────────────────────────────


@router.post("", status_code=201)
async def create_error_report(
    payload: ErrorReportCreate,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict:
    """Crea un reporte. tenant/email vienen del account; el context se redacta."""
    severity = payload.severity if payload.severity in SEVERITIES else "med"
    report = ErrorReport(
        tenant_id=account.tenant_id,
        account_id=account.id,
        reporter_email=account.email,
        message=payload.message.strip(),
        context=_sanitize_context(payload.context),
        severity=severity,
        status="open",
    )
    async with async_session_factory() as db:
        db.add(report)
        await db.commit()
        await db.refresh(report)
        result = _to_dict(report)
    return result


# ── GET / PATCH: triage (super-admin) ────────────────────────────────────────


@router.get("")
async def list_error_reports(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: object = Depends(require_superadmin),
) -> dict:
    offset = (page - 1) * page_size
    async with async_session_factory() as db:
        stmt = select(ErrorReport)
        count_stmt = select(func.count()).select_from(ErrorReport)
        if status in STATUSES:
            stmt = stmt.where(ErrorReport.status == status)
            count_stmt = count_stmt.where(ErrorReport.status == status)
        if severity in SEVERITIES:
            stmt = stmt.where(ErrorReport.severity == severity)
            count_stmt = count_stmt.where(ErrorReport.severity == severity)
        if tenant_id:
            try:
                tid = _uuid.UUID(tenant_id)
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=422, detail="Invalid tenant id") from exc
            stmt = stmt.where(ErrorReport.tenant_id == tid)
            count_stmt = count_stmt.where(ErrorReport.tenant_id == tid)
        total = (await db.execute(count_stmt)).scalar_one()
        rows = (
            (
                await db.execute(
                    stmt.order_by(ErrorReport.created_at.desc()).offset(offset).limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        # Conteo de abiertos para el badge del nav super-admin.
        open_total = (
            await db.execute(
                select(func.count()).select_from(ErrorReport).where(ErrorReport.status == "open")
            )
        ).scalar_one()
        tenant_names = await _tenant_name_map(db)
        items = [_to_dict(r, tenant_names) for r in rows]
    return {
        "items": items,
        "total": total,
        "open_total": open_total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/{report_id}")
async def triage_error_report(
    report_id: str,
    payload: ErrorReportTriage,
    _: object = Depends(require_superadmin),
) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") is not None and updates["status"] not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    if updates.get("severity") is not None and updates["severity"] not in SEVERITIES:
        raise HTTPException(status_code=422, detail="Invalid severity")
    fields = {k: v for k, v in updates.items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        rid = _uuid.UUID(report_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid report id") from exc

    async with async_session_factory() as db:
        report = (
            await db.execute(select(ErrorReport).where(ErrorReport.id == rid))
        ).scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail="Error report not found")
        for key, value in fields.items():
            setattr(report, key, value)
        await db.commit()
        await db.refresh(report)
        result = _to_dict(report)
    return result
