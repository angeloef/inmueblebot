"""
cobranzas.py — API admin de Cobranzas (gestión de alquileres).

Endpoints bajo /admin/* (también expuestos en /api/admin/* vía el compat router
de main.py). Reutiliza la sesión sync, la auth y las migraciones de admin.py.

La lógica de cálculo (aumentos IPC, punitorios día a día, generación de cuotas)
vive en app/services/billing_service.py — scheduler-ready.
"""
from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text as _text

from app.api.routes.admin import get_db, verify_admin_api_key, _get_sync_session
from app.db.models import User, Property, Contract, Charge, ContractExpense, EconomicIndex
from app.services import billing_service as bs

router = APIRouter(prefix="/admin", tags=["cobranzas"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ContractCreate(BaseModel):
    property_id: Optional[int] = None
    tenant_id: Optional[str] = None
    owner_id: Optional[str] = None
    start_date: str                         # ISO date, ej "2026-01-01"
    end_date: Optional[str] = None
    base_rent: int = 0
    currency: str = "ARS"
    payment_due_day: int = 10
    grace_days: int = 0
    adjustment_index: str = "IPC"           # IPC | fixed | none
    adjustment_frequency_months: int = 3
    adjustment_fixed_pct: Optional[float] = None
    punitorio_daily_pct: float = 0.0
    commission_pct: float = 0.0
    status: str = "active"
    notes: Optional[str] = None


class ContractUpdate(BaseModel):
    property_id: Optional[int] = None
    tenant_id: Optional[str] = None
    owner_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    base_rent: Optional[int] = None
    currency: Optional[str] = None
    payment_due_day: Optional[int] = None
    grace_days: Optional[int] = None
    adjustment_index: Optional[str] = None
    adjustment_frequency_months: Optional[int] = None
    adjustment_fixed_pct: Optional[float] = None
    punitorio_daily_pct: Optional[float] = None
    commission_pct: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ChargeUpdate(BaseModel):
    base_amount: Optional[int] = None       # editar el monto a cobrar mes a mes
    due_date: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ChargePay(BaseModel):
    amount_paid: Optional[int] = None        # default: total calculado
    payment_method: Optional[str] = None
    paid_at: Optional[str] = None            # ISO datetime; default ahora


class ExpenseCreate(BaseModel):
    description: str = ""
    amount: int = 0
    category: str = "otro"                   # servicio | expensas | reparacion | otro
    period: Optional[str] = None             # ISO date (mes) si es puntual
    recurring: bool = False
    charge_id: Optional[str] = None


class IndexCreate(BaseModel):
    code: str = "IPC"
    period: str                              # ISO date (se normaliza al mes)
    index_level: Optional[float] = None
    monthly_pct: Optional[float] = None
    source: str = "manual"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Fecha inválida: {s}")


def _as_uuid(s: str, label: str = "id") -> _uuid.UUID:
    try:
        return _uuid.UUID(s)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"{label} inválido (se espera UUID)")


def _index_map(db: Session, code: str = "IPC") -> dict:
    rows = db.query(EconomicIndex).filter(EconomicIndex.code == code).all()
    return bs.build_index_map(rows, code=code)


def _expense_to_dict(e: ContractExpense) -> dict:
    return {
        "id": str(e.id),
        "contract_id": str(e.contract_id),
        "charge_id": str(e.charge_id) if e.charge_id else None,
        "description": e.description or "",
        "amount": e.amount or 0,
        "category": e.category or "otro",
        "period": e.period.isoformat() if e.period else None,
        "recurring": bool(e.recurring),
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _charge_to_dict(charge: Charge, contract: Contract, expenses: List, index_map: dict, as_of: date) -> dict:
    exp = bs.expenses_for_period(expenses, charge.period)
    fig = bs.live_charge_figures(charge, contract, exp, as_of)
    return {
        "id": str(charge.id),
        "contract_id": str(charge.contract_id),
        "period": charge.period.isoformat(),
        "due_date": charge.due_date.isoformat() if charge.due_date else None,
        "base_amount": charge.base_amount or 0,
        "adjustment_amount": charge.adjustment_amount or 0,
        "expenses_amount": fig["expenses_amount"],
        "punitorio_amount": fig["punitorio_amount"],
        "total_amount": fig["total_amount"],
        "amount_paid": charge.amount_paid or 0,
        "outstanding": fig["outstanding"],
        "status": charge.status,
        "display_status": fig["display_status"],
        "paid_at": charge.paid_at.isoformat() if charge.paid_at else None,
        "payment_method": charge.payment_method,
        "reminder_sent_at": charge.reminder_sent_at.isoformat() if charge.reminder_sent_at else None,
        "notes": charge.notes,
    }


def _contract_summary(contract: Contract, expenses: List, index_map: dict, as_of: date) -> dict:
    pending = overdue = balance = 0
    next_due = None
    for ch in contract.charges or []:
        exp = bs.expenses_for_period(expenses, ch.period)
        fig = bs.live_charge_figures(ch, contract, exp, as_of)
        if fig["display_status"] in ("pending", "partial", "overdue"):
            pending += 1
            balance += fig["outstanding"]
            if fig["display_status"] == "overdue":
                overdue += 1
            if ch.due_date and (next_due is None or ch.due_date < next_due):
                next_due = ch.due_date
    cur_rent, _adj, idx_pending = bs.compute_rent_for_period(
        contract, bs.month_start(as_of), index_map
    )
    return {
        "pending_count": pending,
        "overdue_count": overdue,
        "balance": balance,
        "next_due": next_due,
        "current_rent": cur_rent,
        "index_pending": idx_pending,
    }


def _contract_to_dict(db: Session, c: Contract, index_map: dict, as_of: date,
                      include_detail: bool = False) -> dict:
    tenant = db.query(User).filter(User.id == c.tenant_id).first() if c.tenant_id else None
    owner = db.query(User).filter(User.id == c.owner_id).first() if c.owner_id else None
    prop = db.query(Property).filter(Property.id == c.property_id).first() if c.property_id else None
    expenses = list(c.expenses or [])
    summ = _contract_summary(c, expenses, index_map, as_of)
    d = {
        "id": str(c.id),
        "property_id": c.property_id,
        "property_label": (prop.title or prop.location) if prop else None,
        "tenant_id": str(c.tenant_id) if c.tenant_id else None,
        "tenant_name": tenant.name if tenant else None,
        "tenant_phone": (tenant.whatsapp_phone or tenant.bsuid) if tenant else None,
        "owner_id": str(c.owner_id) if c.owner_id else None,
        "owner_name": owner.name if owner else None,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "end_date": c.end_date.isoformat() if c.end_date else None,
        "base_rent": c.base_rent or 0,
        "current_rent": summ["current_rent"],
        "currency": c.currency or "ARS",
        "payment_due_day": c.payment_due_day,
        "grace_days": c.grace_days,
        "adjustment_index": c.adjustment_index,
        "adjustment_frequency_months": c.adjustment_frequency_months,
        "adjustment_fixed_pct": c.adjustment_fixed_pct,
        "punitorio_daily_pct": c.punitorio_daily_pct,
        "commission_pct": c.commission_pct,
        "status": c.status,
        "public_token": c.public_token,
        "notes": c.notes,
        "pending_count": summ["pending_count"],
        "overdue_count": summ["overdue_count"],
        "balance": summ["balance"],
        "next_due": summ["next_due"].isoformat() if summ["next_due"] else None,
        "index_pending": summ["index_pending"],
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    if include_detail:
        d["charges"] = [
            _charge_to_dict(ch, c, expenses, index_map, as_of)
            for ch in sorted(c.charges or [], key=lambda x: x.period, reverse=True)
        ]
        d["expenses"] = [_expense_to_dict(e) for e in expenses]
    return d


def _apply_contract_fields(c: Contract, data: dict) -> None:
    """Aplica campos de un dict (create/update) al objeto Contract."""
    for key in ("base_rent", "currency", "payment_due_day", "grace_days",
                "adjustment_index", "adjustment_frequency_months", "adjustment_fixed_pct",
                "punitorio_daily_pct", "commission_pct", "status", "notes"):
        if key in data and data[key] is not None:
            setattr(c, key, data[key])
    if "property_id" in data:
        c.property_id = data["property_id"]
    if data.get("tenant_id") is not None:
        c.tenant_id = _as_uuid(data["tenant_id"], "tenant_id")
    if data.get("owner_id") is not None:
        c.owner_id = _as_uuid(data["owner_id"], "owner_id")
    if "start_date" in data and data["start_date"]:
        c.start_date = _parse_date(data["start_date"])
    if "end_date" in data:
        c.end_date = _parse_date(data["end_date"])


# ─── Contracts ────────────────────────────────────────────────────────────────

@router.get("/contracts")
def list_contracts(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    as_of = bs.today_ar()
    index_map = _index_map(db)
    contracts = db.query(Contract).order_by(Contract.created_at.desc().nullslast()).all()
    return {
        "contracts": [_contract_to_dict(db, c, index_map, as_of) for c in contracts],
        "total": len(contracts),
    }


@router.post("/contracts")
def create_contract(
    data: ContractCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = Contract(start_date=_parse_date(data.start_date) or bs.today_ar())
    _apply_contract_fields(c, data.model_dump())
    c.public_token = secrets.token_urlsafe(16)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _contract_to_dict(db, c, _index_map(db), bs.today_ar(), include_detail=True)


@router.get("/contracts/{contract_id}")
def get_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return _contract_to_dict(db, c, _index_map(db), bs.today_ar(), include_detail=True)


@router.patch("/contracts/{contract_id}")
def update_contract(
    contract_id: str,
    data: ContractUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    _apply_contract_fields(c, data.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(c)
    return _contract_to_dict(db, c, _index_map(db), bs.today_ar(), include_detail=True)


@router.delete("/contracts/{contract_id}")
def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    db.delete(c)
    db.commit()
    return {"status": "deleted", "contract_id": contract_id}


# ─── Charges ──────────────────────────────────────────────────────────────────

@router.post("/contracts/{contract_id}/charges/generate")
def generate_charges(
    contract_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Genera las cuotas faltantes hasta el mes actual (idempotente)."""
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    index_map = _index_map(db)
    created = bs.ensure_charges(db, c, Charge, expenses=list(c.expenses or []), index_map=index_map)
    db.commit()
    db.refresh(c)
    return {
        "status": "ok",
        "created": created,
        "contract": _contract_to_dict(db, c, index_map, bs.today_ar(), include_detail=True),
    }


@router.get("/contracts/{contract_id}/charges")
def list_charges(
    contract_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    as_of = bs.today_ar()
    index_map = _index_map(db)
    expenses = list(c.expenses or [])
    charges = sorted(c.charges or [], key=lambda x: x.period, reverse=True)
    return {"charges": [_charge_to_dict(ch, c, expenses, index_map, as_of) for ch in charges]}


@router.patch("/charges/{charge_id}")
def update_charge(
    charge_id: str,
    data: ChargeUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    ch = db.query(Charge).filter(Charge.id == _as_uuid(charge_id, "charge_id")).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Cobro no encontrado")
    updates = data.model_dump(exclude_unset=True)
    if "base_amount" in updates and updates["base_amount"] is not None:
        ch.base_amount = updates["base_amount"]
    if "due_date" in updates:
        ch.due_date = _parse_date(updates["due_date"])
    if updates.get("status"):
        ch.status = updates["status"]
    if "notes" in updates:
        ch.notes = updates["notes"]
    db.commit()
    db.refresh(ch)
    c = ch.contract
    return _charge_to_dict(ch, c, list(c.expenses or []), _index_map(db), bs.today_ar())


@router.post("/charges/{charge_id}/pay")
def pay_charge(
    charge_id: str,
    data: ChargePay,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Marca un cobro como pagado, congelando gastos y punitorios al día de pago."""
    ch = db.query(Charge).filter(Charge.id == _as_uuid(charge_id, "charge_id")).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Cobro no encontrado")
    c = ch.contract
    paid_at = None
    if data.paid_at:
        try:
            paid_at = datetime.fromisoformat(data.paid_at)
        except ValueError:
            paid_at = None
    paid_at = paid_at or datetime.now(bs._AR_TZ)
    as_of = paid_at.date()

    # Congelar cifras al día de pago.
    exp = bs.expenses_for_period(list(c.expenses or []), ch.period)
    fig = bs.live_charge_figures(ch, c, exp, as_of)
    ch.expenses_amount = fig["expenses_amount"]
    ch.punitorio_amount = fig["punitorio_amount"]
    ch.total_amount = fig["total_amount"]
    ch.amount_paid = data.amount_paid if data.amount_paid is not None else fig["total_amount"]
    ch.payment_method = data.payment_method
    ch.paid_at = paid_at
    ch.status = "paid" if ch.amount_paid >= ch.total_amount else "partial"
    db.commit()
    db.refresh(ch)
    return _charge_to_dict(ch, c, list(c.expenses or []), _index_map(db), bs.today_ar())


@router.post("/charges/{charge_id}/remind")
async def remind_charge(
    charge_id: str,
    _: bool = Depends(verify_admin_api_key),
):
    """Envía un recordatorio de pago por WhatsApp al inquilino (manual)."""
    from app.integrations.whatsapp import send_whatsapp_message

    cid = _as_uuid(charge_id, "charge_id")
    # 1) Reunir datos en una sesión sync corta y cerrarla antes del await.
    db = _get_sync_session()
    try:
        ch = db.query(Charge).filter(Charge.id == cid).first()
        if not ch:
            raise HTTPException(status_code=404, detail="Cobro no encontrado")
        c = ch.contract
        tenant = db.query(User).filter(User.id == c.tenant_id).first() if c.tenant_id else None
        phone = (tenant.whatsapp_phone if tenant else None)
        if not phone:
            raise HTTPException(status_code=400, detail="El inquilino no tiene teléfono cargado")
        row = db.execute(_text("SELECT value FROM bot_settings WHERE key='company_name'")).fetchone()
        company = row[0] if row else ""
        exp = bs.expenses_for_period(list(c.expenses or []), ch.period)
        fig = bs.live_charge_figures(ch, c, exp, bs.today_ar())
        message = bs.build_reminder_message(
            c, ch, fig, company_name=company,
            tenant_name=(tenant.name or "") if tenant else "",
            currency=c.currency or "ARS",
        )
    finally:
        db.close()

    # 2) Enviar (async) fuera de la sesión.
    ok = await send_whatsapp_message(phone, message)

    # 3) Registrar el envío.
    if ok:
        db2 = _get_sync_session()
        try:
            db2.execute(
                _text("UPDATE charges SET reminder_sent_at = NOW() WHERE id = :id"),
                {"id": str(cid)},
            )
            db2.commit()
        finally:
            db2.close()

    return {"status": "sent" if ok else "error", "phone": phone, "message": message}


# ─── Expenses ─────────────────────────────────────────────────────────────────

@router.get("/contracts/{contract_id}/expenses")
def list_expenses(
    contract_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"expenses": [_expense_to_dict(e) for e in (c.expenses or [])]}


@router.post("/contracts/{contract_id}/expenses")
def create_expense(
    contract_id: str,
    data: ExpenseCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    e = ContractExpense(
        contract_id=c.id,
        charge_id=_as_uuid(data.charge_id, "charge_id") if data.charge_id else None,
        description=data.description or "",
        amount=data.amount or 0,
        category=data.category or "otro",
        period=_parse_date(data.period),
        recurring=bool(data.recurring),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _expense_to_dict(e)


@router.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    e = db.query(ContractExpense).filter(ContractExpense.id == _as_uuid(expense_id, "expense_id")).first()
    if not e:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    db.delete(e)
    db.commit()
    return {"status": "deleted", "expense_id": expense_id}


# ─── Economic indices (IPC) ───────────────────────────────────────────────────

@router.get("/indices")
def list_indices(
    code: str = "IPC",
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    rows = (
        db.query(EconomicIndex)
        .filter(EconomicIndex.code == code)
        .order_by(EconomicIndex.period.desc())
        .all()
    )
    return {
        "indices": [
            {
                "id": r.id,
                "code": r.code,
                "period": r.period.isoformat(),
                "index_level": r.index_level,
                "monthly_pct": r.monthly_pct,
                "source": r.source,
            }
            for r in rows
        ]
    }


@router.post("/indices")
def upsert_index(
    data: IndexCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Carga (o actualiza) el valor de un índice para un mes (upsert por code+period)."""
    period = bs.month_start(_parse_date(data.period))
    row = (
        db.query(EconomicIndex)
        .filter(EconomicIndex.code == data.code, EconomicIndex.period == period)
        .first()
    )
    if row is None:
        row = EconomicIndex(code=data.code, period=period)
        db.add(row)
    row.index_level = data.index_level
    row.monthly_pct = data.monthly_pct
    row.source = data.source or "manual"
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "code": row.code,
        "period": row.period.isoformat(),
        "index_level": row.index_level,
        "monthly_pct": row.monthly_pct,
        "source": row.source,
    }


# ─── Summary & liquidación ────────────────────────────────────────────────────

@router.get("/cobranzas/summary")
def cobranzas_summary(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """KPIs del panel: a cobrar, cobrado del mes, pendientes y vencidos."""
    as_of = bs.today_ar()
    cur_month = bs.month_start(as_of)
    index_map = _index_map(db)
    contracts = db.query(Contract).all()

    to_collect = collected_month = pending_count = overdue_count = 0
    active_contracts = 0
    for c in contracts:
        if c.status == "active":
            active_contracts += 1
        expenses = list(c.expenses or [])
        for ch in (c.charges or []):
            exp = bs.expenses_for_period(expenses, ch.period)
            fig = bs.live_charge_figures(ch, c, exp, as_of)
            if fig["display_status"] in ("pending", "partial", "overdue"):
                to_collect += fig["outstanding"]
                pending_count += 1
                if fig["display_status"] == "overdue":
                    overdue_count += 1
            if ch.status == "paid" and ch.paid_at and bs.month_start(ch.paid_at.date()) == cur_month:
                collected_month += ch.amount_paid or 0

    return {
        "to_collect": to_collect,
        "collected_this_month": collected_month,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "active_contracts": active_contracts,
        "total_contracts": len(contracts),
    }


@router.get("/contracts/{contract_id}/liquidacion")
def liquidacion(
    contract_id: str,
    period: Optional[str] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Liquidación al propietario para un mes: cobrado − comisión − gastos."""
    c = db.query(Contract).filter(Contract.id == _as_uuid(contract_id, "contract_id")).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    pm = bs.month_start(_parse_date(period) or bs.today_ar())
    expenses = list(c.expenses or [])
    charge = next((ch for ch in (c.charges or []) if bs.month_start(ch.period) == pm), None)

    collected = (charge.amount_paid or 0) if charge else 0
    exp_amount = bs.expenses_for_period(expenses, pm)
    commission_pct = c.commission_pct or 0.0
    commission_amount = round(collected * commission_pct / 100.0)
    owner_net = collected - commission_amount - exp_amount

    return {
        "contract_id": str(c.id),
        "period": pm.isoformat(),
        "collected": collected,
        "commission_pct": commission_pct,
        "commission_amount": commission_amount,
        "expenses_amount": exp_amount,
        "owner_net": owner_net,
        "currency": c.currency or "ARS",
        "paid": bool(charge and charge.status == "paid"),
    }
