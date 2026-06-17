"""Explorador global cross-tenant para la consola super-admin (plan 05).

Endpoints ``/admin/global/*`` que listan y editan entidades de **todas** las
inmobiliarias en una sola request. El acceso cross-tenant lo habilita el GUC
``app.is_superadmin`` que setea ``require_superadmin`` (plan 04): dentro de la
request, las políticas RLS exponen filas de cualquier tenant (USING + WITH CHECK).

Diseño:
  - **No reinventa** la serialización: reusa ``_user_to_dict`` / ``_prop_to_dict`` /
    ``_apt_to_dict`` de ``admin.py`` y les agrega ``tenant_id`` + ``tenant_name``.
  - **Edición acotada**: cada entidad tiene un schema de update con whitelist estricta
    (Pydantic). No se ejecutan reglas de negocio nuevas: se aplican campos conocidos.
  - **Auditoría**: cada PATCH emite ``activity_log`` con ``actor='superadmin:<id>'`` y
    el diff de campos, reusando la tabla del plan 03.
  - **Fail-closed**: todo cuelga de ``require_superadmin`` ⇒ cualquier no-superadmin → 403.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import require_superadmin
from app.api.routes.admin import (
    _apt_to_dict,
    _make_async_session,
    _parse_extra,
    _prop_to_dict,
    _user_to_dict,
)
from app.db.models import TenantAccount
from app.services.activity_log_service import log_activity_async

router = APIRouter(prefix="/admin/global", tags=["admin-global"])

# Paginación: defaults conservadores; el tope evita queries sin límite cross-tenant.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

ENTITIES = ("clients", "properties", "appointments")


# ── Schemas de update (whitelist estricta por entidad) ───────────────────────


class ClientGlobalUpdate(BaseModel):
    """Campos editables de un cliente (tabla ``users``) desde super-admin."""

    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=4000)


class PropertyGlobalUpdate(BaseModel):
    """Campos editables de una propiedad desde super-admin."""

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    status: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=500)
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    area_m2: float | None = Field(default=None, ge=0)


class AppointmentGlobalUpdate(BaseModel):
    """Campos editables de una cita desde super-admin."""

    status: str | None = Field(default=None, max_length=40)
    type: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=4000)


# Allowlist de columnas escribibles a nivel ORM. ``location`` se maneja aparte (sincroniza
# extra_data). Nunca incluir id / tenant_id / created_at: la edición jamás reasigna tenant.
_PROPERTY_WRITABLE = frozenset(
    {"title", "description", "price", "currency", "status", "bedrooms", "bathrooms", "area_m2"}
)
_APPOINTMENT_WRITABLE = frozenset({"status", "type", "notes"})


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _tenant_name_map(db) -> dict[str, str]:  # noqa: ANN001
    """id(str) → nombre legible de la inmobiliaria, para anotar cada fila."""
    from app.db.models.tenant import Tenant

    rows = (await db.execute(select(Tenant))).scalars().all()
    return {
        str(t.id): (t.display_name or t.company_name or t.slug or str(t.id))
        for t in rows
    }


def _with_tenant(row_dict: dict, tenant_id: object, names: dict[str, str]) -> dict:
    """Agrega tenant_id (columna RLS real) + nombre de inmobiliaria a la fila."""
    tid = str(tenant_id) if tenant_id else None
    return {
        **row_dict,
        "tenant_id": tid,
        "tenant_name": names.get(tid) if tid else None,
    }


def _superadmin_actor(account: TenantAccount | None) -> str:
    """Identidad del editor para el audit log. La ops-key global no trae account."""
    return f"superadmin:{account.id}" if account is not None else "superadmin:ops"


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    return (page - 1) * size, size


# ── Listados cross-tenant ────────────────────────────────────────────────────


@router.get("/clients")
async def list_global_clients(
    tenant_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: object = Depends(require_superadmin),
) -> dict:
    from app.db.models import User

    offset, size = _paginate(page, page_size)
    async with _make_async_session() as db:
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)
        if tenant_id:
            tid = _uuid.UUID(tenant_id)
            stmt = stmt.where(User.tenant_id == tid)
            count_stmt = count_stmt.where(User.tenant_id == tid)
        if q:
            like = f"%{q}%"
            cond = or_(User.name.ilike(like), User.whatsapp_phone.ilike(like))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        total = (await db.execute(count_stmt)).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(User.created_at.desc().nullslast()).offset(offset).limit(size)
            )
        ).scalars().all()
        names = await _tenant_name_map(db)
        items = [_with_tenant(_user_to_dict(u), u.tenant_id, names) for u in rows]
    return {"items": items, "total": total, "page": page, "page_size": size}


@router.get("/properties")
async def list_global_properties(
    tenant_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: object = Depends(require_superadmin),
) -> dict:
    from app.db.models import Property

    offset, size = _paginate(page, page_size)
    async with _make_async_session() as db:
        stmt = select(Property)
        count_stmt = select(func.count()).select_from(Property)
        if tenant_id:
            tid = _uuid.UUID(tenant_id)
            stmt = stmt.where(Property.tenant_id == tid)
            count_stmt = count_stmt.where(Property.tenant_id == tid)
        if q:
            like = f"%{q}%"
            cond = or_(Property.title.ilike(like), Property.location.ilike(like))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        total = (await db.execute(count_stmt)).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(Property.created_at.desc().nullslast()).offset(offset).limit(size)
            )
        ).scalars().all()
        names = await _tenant_name_map(db)
        # include_images=False: la grilla global no necesita el base64 pesado.
        items = [
            _with_tenant(_prop_to_dict(p, include_images=False), p.tenant_id, names)
            for p in rows
        ]
    return {"items": items, "total": total, "page": page, "page_size": size}


@router.get("/appointments")
async def list_global_appointments(
    tenant_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: object = Depends(require_superadmin),
) -> dict:
    from app.db.models import Appointment

    offset, size = _paginate(page, page_size)
    async with _make_async_session() as db:
        stmt = select(Appointment)
        count_stmt = select(func.count()).select_from(Appointment)
        if tenant_id:
            tid = _uuid.UUID(tenant_id)
            stmt = stmt.where(Appointment.tenant_id == tid)
            count_stmt = count_stmt.where(Appointment.tenant_id == tid)
        if q:
            like = f"%{q}%"
            cond = or_(Appointment.notes.ilike(like), Appointment.type.ilike(like))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        total = (await db.execute(count_stmt)).scalar_one()
        rows = (
            await db.execute(
                stmt.order_by(Appointment.start_time.desc().nullslast()).offset(offset).limit(size)
            )
        ).scalars().all()
        names = await _tenant_name_map(db)
        items = [_with_tenant(_apt_to_dict(a), a.tenant_id, names) for a in rows]
    return {"items": items, "total": total, "page": page, "page_size": size}


# ── Edición full cross-tenant ────────────────────────────────────────────────


async def _patch_client(db, entity_id: str, updates: dict) -> tuple[dict, dict, Any]:  # noqa: ANN001
    from app.db.models import User

    user = (
        await db.execute(select(User).where(User.id == _uuid.UUID(entity_id)))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")
    if "name" in updates:
        user.name = updates["name"]
    extra = dict(_parse_extra(getattr(user, "extra_data", None)))
    for key in ("email", "role", "notes"):
        if key in updates:
            extra[key] = updates[key]
    user.extra_data = extra
    diff = {k: {"to": updates[k]} for k in updates}
    return _user_to_dict(user), diff, user.tenant_id


async def _patch_property(db, entity_id: str, updates: dict) -> tuple[dict, dict, Any]:  # noqa: ANN001
    from app.db.models import Property

    try:
        pid = int(entity_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid property id") from exc
    prop = (
        await db.execute(select(Property).where(Property.id == pid))
    ).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    before = {k: getattr(prop, k, None) for k in updates if hasattr(prop, k)}
    if "location" in updates:
        prop.location = updates.pop("location")
        extra = dict(prop.extra_data or {})
        extra["street"] = prop.location.split(",")[0].strip() if prop.location else ""
        prop.extra_data = extra
    # Allowlist explícita a nivel ORM (defensa en profundidad sobre la whitelist Pydantic):
    # nunca dejar que un campo coincidente con una columna sensible (id/tenant_id) se escriba.
    for key, value in updates.items():
        if key in _PROPERTY_WRITABLE:
            setattr(prop, key, value)
    diff = {
        k: {"from": before.get(k), "to": getattr(prop, k, None)}
        for k in before
        if before.get(k) != getattr(prop, k, None)
    }
    return _prop_to_dict(prop, include_images=False), diff, prop.tenant_id


async def _patch_appointment(db, entity_id: str, updates: dict) -> tuple[dict, dict, Any]:  # noqa: ANN001
    from app.db.models import Appointment

    apt = (
        await db.execute(select(Appointment).where(Appointment.id == _uuid.UUID(entity_id)))
    ).scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    before = {k: getattr(apt, k, None) for k in updates if hasattr(apt, k)}
    for key, value in updates.items():
        if key in _APPOINTMENT_WRITABLE:
            setattr(apt, key, value)
    diff = {
        k: {"from": before.get(k), "to": getattr(apt, k, None)}
        for k in before
        if before.get(k) != getattr(apt, k, None)
    }
    return _apt_to_dict(apt), diff, apt.tenant_id


_PATCH_SCHEMAS: dict[str, type[BaseModel]] = {
    "clients": ClientGlobalUpdate,
    "properties": PropertyGlobalUpdate,
    "appointments": AppointmentGlobalUpdate,
}
_PATCH_HANDLERS = {
    "clients": (_patch_client, "user"),
    "properties": (_patch_property, "property"),
    "appointments": (_patch_appointment, "appointment"),
}


@router.patch("/{entity}/{entity_id}")
async def patch_global_entity(
    entity: str,
    entity_id: str,
    payload: dict,
    account: TenantAccount | None = Depends(require_superadmin),  # noqa: B008
) -> dict:
    """Edición full cross-tenant de una entidad. Audita el cambio en ``activity_log``.

    El body se valida contra el schema de la entidad (whitelist estricta). Solo se
    aplican los campos enviados; cada cambio queda registrado con el actor super-admin.
    """
    if entity not in _PATCH_HANDLERS:
        raise HTTPException(status_code=404, detail="Unknown entity")

    schema = _PATCH_SCHEMAS[entity]
    updates = schema(**payload).model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    handler, entity_type = _PATCH_HANDLERS[entity]
    async with _make_async_session() as db:
        result, diff, tenant_id = await handler(db, entity_id, dict(updates))
        if diff:
            await log_activity_async(
                db,
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action="superadmin_edited",
                actor=_superadmin_actor(account),
                payload={"changes": diff},
            )
        await db.commit()
    return result
