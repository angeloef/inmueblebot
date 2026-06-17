"""
operations.py — API admin de operaciones inmobiliarias.

Fase crítica del plan ImplementacionesWIP/04_gestion-operaciones-inmobiliarias.md:
  - property_relations: vínculos cliente↔propiedad relacionales (reemplaza JSONB).
  - guarantors: garantes de contratos.
  - sales: operaciones de venta.
  - backfill: migra los vínculos viejos (extra_data JSONB) a property_relations.

Mismo patrón que cobranzas.py: sesión sync de admin, auth get_current_account,
y creación de schema en transacción AISLADA (evita el landmine de la migración
monolítica de admin.py).
"""
from __future__ import annotations

import threading
import uuid as _uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as _text
from sqlalchemy.orm import Session

from app.api.deps import get_current_account
from app.api.routes.admin import get_db, _get_sync_session, _parse_extra
import app.api.routes.admin as _admin
from app.core.tenancy import resolve_tenant_id
from app.db.models import User, Property, Contract, PropertyRelation, Guarantor, Sale

import logging
logger = logging.getLogger(__name__)

VALID_RELATIONS = ("buyer", "tenant", "interested", "owner")
VALID_SALE_STATUS = ("reserved", "signed", "closed", "fallen")
VALID_GUARANTEE_TYPES = ("propietaria", "recibo", "caucion", "otro")

# ─── Creación de schema (transacción aislada, idempotente) ────────────────────
_OPERATIONS_DDL = [
    """
    CREATE TABLE IF NOT EXISTS property_relations (
        id UUID PRIMARY KEY,
        tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
        property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
        client_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        relation VARCHAR(20) NOT NULL,
        agent_id UUID REFERENCES tenant_members(id) ON DELETE SET NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ended_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS guarantors (
        id UUID PRIMARY KEY,
        tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
        contract_id UUID REFERENCES contracts(id) ON DELETE CASCADE,
        client_id UUID REFERENCES users(id) ON DELETE SET NULL,
        name VARCHAR(200) NOT NULL DEFAULT '',
        guarantee_type VARCHAR(20) NOT NULL DEFAULT 'otro',
        phone VARCHAR(40),
        email VARCHAR(255),
        guarantee_property_address VARCHAR(300),
        notes VARCHAR(1000),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sales (
        id UUID PRIMARY KEY,
        tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
        property_id INTEGER REFERENCES properties(id) ON DELETE SET NULL,
        buyer_id UUID REFERENCES users(id) ON DELETE SET NULL,
        seller_id UUID REFERENCES users(id) ON DELETE SET NULL,
        agent_id UUID REFERENCES tenant_members(id) ON DELETE SET NULL,
        sale_price BIGINT NOT NULL DEFAULT 0,
        currency VARCHAR(3) NOT NULL DEFAULT 'USD',
        reservation_amount BIGINT NOT NULL DEFAULT 0,
        reservation_date DATE,
        sale_date DATE,
        commission_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
        commission_amount BIGINT NOT NULL DEFAULT 0,
        status VARCHAR(20) NOT NULL DEFAULT 'reserved',
        notes VARCHAR(2000),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_property_relations_property ON property_relations(tenant_id, property_id)",
    "CREATE INDEX IF NOT EXISTS ix_property_relations_client ON property_relations(tenant_id, client_id)",
    "CREATE INDEX IF NOT EXISTS ix_guarantors_contract ON guarantors(tenant_id, contract_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_property ON sales(tenant_id, property_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_status ON sales(tenant_id, status)",
]

# ALTERs idempotentes en tablas PREEXISTENTES (contracts, appointments). Corren
# SIEMPRE —aún si property_relations ya existe— porque columnas nuevas se agregan en
# deploys posteriores y el fast-path del CREATE las saltearía. Son baratos e IF NOT EXISTS.
_OPERATIONS_ALTERS = [
    # C3/C5: columnas de depósito + atribución de agente en contracts.
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES tenant_members(id) ON DELETE SET NULL",
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS deposit_amount BIGINT NOT NULL DEFAULT 0",
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS deposit_currency VARCHAR(3) NOT NULL DEFAULT 'ARS'",
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS deposit_status VARCHAR(20) NOT NULL DEFAULT 'none'",
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS deposit_returned_at TIMESTAMPTZ",
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS deposit_notes VARCHAR(500)",
    # C5 (visitas): atribución de agente en appointments. SIN FK: appointments es una
    # tabla caliente (el bot escribe citas); ADD COLUMN con FK necesitaría lock sobre
    # appointments + tenant_members y con lock_timeout corto se caería. Columna plana
    # UUID = metadata-only (instantáneo). La integridad la cubre el ORM (relación lógica).
    "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS agent_id UUID",
]

_schema_ready = False
_schema_lock = threading.Lock()


def ensure_operations_schema() -> None:
    """Crea las tablas de operaciones en transacción aislada (idempotente, seguro)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        _get_sync_session().close()
        engine = _admin._engine
        if engine is None:
            return
        try:
            with engine.connect() as conn:
                exists = conn.execute(
                    _text("SELECT to_regclass('public.property_relations')")
                ).scalar()
            # CREATE solo si faltan las tablas base (una transacción).
            if not exists:
                with engine.begin() as conn:
                    conn.execute(_text("SET LOCAL lock_timeout = '4s'"))
                    for stmt in _OPERATIONS_DDL:
                        conn.execute(_text(stmt))
            # ALTERs idempotentes: SIEMPRE y cada uno en su PROPIA transacción, así un
            # fallo/timeout (p. ej. lock en una tabla caliente) no aborta a los demás.
            for stmt in _OPERATIONS_ALTERS:
                try:
                    with engine.begin() as conn:
                        conn.execute(_text("SET LOCAL lock_timeout = '4s'"))
                        conn.execute(_text(stmt))
                except Exception as e2:
                    logger.warning("operations ALTER diferido: %s", e2)
            _schema_ready = True
            logger.info("Operations schema ensured (isolated transaction)")
        except Exception as e:
            logger.warning("ensure_operations_schema deferred: %s", e)


router = APIRouter(
    prefix="/admin", tags=["operations"],
    dependencies=[Depends(ensure_operations_schema)],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _as_uuid(s: str, label: str = "id") -> _uuid.UUID:
    try:
        return _uuid.UUID(str(s))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail=f"Invalid {label} format (expected UUID)")


def _opt_uuid(s: Optional[str], label: str) -> Optional[_uuid.UUID]:
    if s is None or s == "":
        return None
    return _as_uuid(s, label)


def _rel_to_dict(r: PropertyRelation) -> dict:
    return {
        "id": str(r.id),
        "property_id": r.property_id,
        "client_id": str(r.client_id),
        "relation": r.relation,
        "agent_id": str(r.agent_id) if r.agent_id else None,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
    }


def _guarantor_to_dict(g: Guarantor) -> dict:
    return {
        "id": str(g.id),
        "contract_id": str(g.contract_id) if g.contract_id else None,
        "client_id": str(g.client_id) if g.client_id else None,
        "name": g.name,
        "guarantee_type": g.guarantee_type,
        "phone": g.phone,
        "email": g.email,
        "guarantee_property_address": g.guarantee_property_address,
        "notes": g.notes,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


def _sale_to_dict(s: Sale) -> dict:
    return {
        "id": str(s.id),
        "property_id": s.property_id,
        "buyer_id": str(s.buyer_id) if s.buyer_id else None,
        "seller_id": str(s.seller_id) if s.seller_id else None,
        "agent_id": str(s.agent_id) if s.agent_id else None,
        "sale_price": s.sale_price,
        "currency": s.currency,
        "reservation_amount": s.reservation_amount,
        "reservation_date": s.reservation_date.isoformat() if s.reservation_date else None,
        "sale_date": s.sale_date.isoformat() if s.sale_date else None,
        "commission_pct": s.commission_pct,
        "commission_amount": s.commission_amount,
        "status": s.status,
        "notes": s.notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _parse_date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


# ─── Property relations ─────────────────────────────────────────────────────────

class RelationCreate(BaseModel):
    property_id: int
    client_id: str
    relation: str = "interested"
    agent_id: Optional[str] = None


@router.get("/property-relations")
def list_relations(
    property_id: Optional[int] = None,
    client_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    q = db.query(PropertyRelation).filter(PropertyRelation.status == "active")
    if property_id is not None:
        q = q.filter(PropertyRelation.property_id == property_id)
    if client_id:
        q = q.filter(PropertyRelation.client_id == _as_uuid(client_id, "client_id"))
    rows = q.order_by(PropertyRelation.created_at.desc()).all()
    return {"relations": [_rel_to_dict(r) for r in rows]}


@router.post("/property-relations")
def create_relation(
    data: RelationCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    if data.relation not in VALID_RELATIONS:
        raise HTTPException(status_code=422, detail=f"relation inválida (esperado {VALID_RELATIONS})")
    cid = _as_uuid(data.client_id, "client_id")
    if not db.query(Property).filter(Property.id == data.property_id).first():
        raise HTTPException(status_code=404, detail="Property not found")
    if not db.query(User).filter(User.id == cid).first():
        raise HTTPException(status_code=404, detail="Client not found")
    rel = upsert_relation(
        db, property_id=data.property_id, client_id=cid,
        relation=data.relation, agent_id=_opt_uuid(data.agent_id, "agent_id"),
    )
    db.commit()
    db.refresh(rel)
    return _rel_to_dict(rel)


@router.delete("/property-relations/{relation_id}")
def end_relation(
    relation_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    r = db.query(PropertyRelation).filter(PropertyRelation.id == _as_uuid(relation_id, "relation_id")).first()
    if not r:
        raise HTTPException(status_code=404, detail="Relation not found")
    r.status = "ended"
    r.ended_at = datetime.utcnow()
    db.commit()
    return {"status": "ended", "id": relation_id}


def upsert_relation(db: Session, *, property_id: int, client_id: _uuid.UUID,
                    relation: str, agent_id: Optional[_uuid.UUID] = None) -> PropertyRelation:
    """Crea o reactiva una relación activa (property, client, relation). Idempotente.

    Reutilizable desde relate-client (admin.py) para escribir el modelo relacional.
    NO commitea: el caller maneja la transacción.
    """
    existing = (
        db.query(PropertyRelation)
        .filter(
            PropertyRelation.property_id == property_id,
            PropertyRelation.client_id == client_id,
            PropertyRelation.relation == relation,
            PropertyRelation.status == "active",
        )
        .first()
    )
    if existing:
        if agent_id is not None:
            existing.agent_id = agent_id
        return existing
    rel = PropertyRelation(
        tenant_id=resolve_tenant_id(),
        property_id=property_id,
        client_id=client_id,
        relation=relation,
        agent_id=agent_id,
        status="active",
    )
    db.add(rel)
    return rel


# ─── Guarantors ─────────────────────────────────────────────────────────────────

class GuarantorCreate(BaseModel):
    contract_id: Optional[str] = None
    client_id: Optional[str] = None
    name: str = ""
    guarantee_type: str = "otro"
    phone: Optional[str] = None
    email: Optional[str] = None
    guarantee_property_address: Optional[str] = None
    notes: Optional[str] = None


@router.get("/contracts/{contract_id}/guarantors")
def list_guarantors(
    contract_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    cid = _as_uuid(contract_id, "contract_id")
    rows = db.query(Guarantor).filter(Guarantor.contract_id == cid).order_by(Guarantor.created_at).all()
    return {"guarantors": [_guarantor_to_dict(g) for g in rows]}


@router.post("/contracts/{contract_id}/guarantors")
def create_guarantor(
    contract_id: str,
    data: GuarantorCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    cid = _as_uuid(contract_id, "contract_id")
    if not db.query(Contract).filter(Contract.id == cid).first():
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    if data.guarantee_type not in VALID_GUARANTEE_TYPES:
        raise HTTPException(status_code=422, detail=f"guarantee_type inválido (esperado {VALID_GUARANTEE_TYPES})")
    g = Guarantor(
        tenant_id=resolve_tenant_id(),
        contract_id=cid,
        client_id=_opt_uuid(data.client_id, "client_id"),
        name=data.name or "",
        guarantee_type=data.guarantee_type,
        phone=data.phone,
        email=data.email,
        guarantee_property_address=data.guarantee_property_address,
        notes=data.notes,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return _guarantor_to_dict(g)


@router.delete("/guarantors/{guarantor_id}")
def delete_guarantor(
    guarantor_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    g = db.query(Guarantor).filter(Guarantor.id == _as_uuid(guarantor_id, "guarantor_id")).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garante no encontrado")
    db.delete(g)
    db.commit()
    return {"status": "deleted", "id": guarantor_id}


# ─── Sales ────────────────────────────────────────────────────────────────────

class SaleCreate(BaseModel):
    property_id: Optional[int] = None
    buyer_id: Optional[str] = None
    seller_id: Optional[str] = None
    agent_id: Optional[str] = None
    sale_price: int = 0
    currency: str = "USD"
    reservation_amount: int = 0
    reservation_date: Optional[str] = None
    sale_date: Optional[str] = None
    commission_pct: float = 0.0
    status: str = "reserved"
    notes: Optional[str] = None


class SaleUpdate(BaseModel):
    sale_price: Optional[int] = None
    currency: Optional[str] = None
    reservation_amount: Optional[int] = None
    reservation_date: Optional[str] = None
    sale_date: Optional[str] = None
    commission_pct: Optional[float] = None
    status: Optional[str] = None
    agent_id: Optional[str] = None
    notes: Optional[str] = None


def _apply_commission(s: Sale) -> None:
    s.commission_amount = round((s.sale_price or 0) * (s.commission_pct or 0.0) / 100.0)


@router.get("/sales")
def list_sales(
    property_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    q = db.query(Sale)
    if property_id is not None:
        q = q.filter(Sale.property_id == property_id)
    rows = q.order_by(Sale.created_at.desc()).all()
    return {"sales": [_sale_to_dict(s) for s in rows]}


@router.post("/sales")
def create_sale(
    data: SaleCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    if data.status not in VALID_SALE_STATUS:
        raise HTTPException(status_code=422, detail=f"status inválido (esperado {VALID_SALE_STATUS})")
    s = Sale(
        tenant_id=resolve_tenant_id(),
        property_id=data.property_id,
        buyer_id=_opt_uuid(data.buyer_id, "buyer_id"),
        seller_id=_opt_uuid(data.seller_id, "seller_id"),
        agent_id=_opt_uuid(data.agent_id, "agent_id"),
        sale_price=data.sale_price or 0,
        currency=data.currency or "USD",
        reservation_amount=data.reservation_amount or 0,
        reservation_date=_parse_date(data.reservation_date),
        sale_date=_parse_date(data.sale_date),
        commission_pct=data.commission_pct or 0.0,
        status=data.status,
        notes=data.notes,
    )
    _apply_commission(s)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _sale_to_dict(s)


@router.patch("/sales/{sale_id}")
def update_sale(
    sale_id: str,
    data: SaleUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    s = db.query(Sale).filter(Sale.id == _as_uuid(sale_id, "sale_id")).first()
    if not s:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    u = data.model_dump(exclude_unset=True)
    if "status" in u and u["status"] not in VALID_SALE_STATUS:
        raise HTTPException(status_code=422, detail=f"status inválido (esperado {VALID_SALE_STATUS})")
    for field in ("sale_price", "currency", "reservation_amount", "commission_pct", "status", "notes"):
        if field in u and u[field] is not None:
            setattr(s, field, u[field])
    if "reservation_date" in u:
        s.reservation_date = _parse_date(u["reservation_date"])
    if "sale_date" in u:
        s.sale_date = _parse_date(u["sale_date"])
    if "agent_id" in u:
        s.agent_id = _opt_uuid(u["agent_id"], "agent_id")
    _apply_commission(s)
    db.commit()
    db.refresh(s)
    return _sale_to_dict(s)


@router.delete("/sales/{sale_id}")
def delete_sale(
    sale_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    s = db.query(Sale).filter(Sale.id == _as_uuid(sale_id, "sale_id")).first()
    if not s:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    db.delete(s)
    db.commit()
    return {"status": "deleted", "id": sale_id}


# ─── Backfill (JSONB → property_relations) ───────────────────────────────────────

@router.post("/operations/backfill")
def backfill_relations(
    db: Session = Depends(get_db),
    _: bool = Depends(get_current_account),
):
    """Migra los vínculos viejos de users.extra_data.property_relations a la tabla
    relacional. Idempotente: no duplica relaciones activas ya existentes."""
    created = 0
    scanned = 0
    users = db.query(User).all()
    for u in users:
        extra = _parse_extra(getattr(u, "extra_data", None))
        rels = extra.get("property_relations", []) or []
        for r in rels:
            scanned += 1
            pid = r.get("prop_id")
            relation = r.get("relation")
            if pid is None or relation not in VALID_RELATIONS:
                continue
            rel = upsert_relation(db, property_id=int(pid), client_id=u.id, relation=relation)
            if rel in db.new:
                created += 1
    db.commit()
    return {"status": "ok", "scanned": scanned, "created": created}
