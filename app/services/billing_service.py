"""
billing_service.py — Lógica de cobranzas (cálculo de aumentos, punitorios y
generación de cuotas).

Todo es **puro e idempotente**: hoy estas funciones se disparan manualmente
desde el panel (botón "Generar cobros", "Marcar pagado", "Recordar"), pero un
scheduler futuro podrá llamarlas tal cual, sin tocar este módulo.

Convenciones:
  - Los montos son enteros (en la moneda del contrato).
  - Los "períodos" son fechas con el primer día del mes (date(Y, M, 1)).
  - Los aumentos por IPC se calculan con niveles de índice:
        renta(período) = base_rent * nivel[mes_ajuste] / nivel[mes_inicio]
    (el producto de coeficientes telescopa al cociente de niveles).
  - Los punitorios se calculan al vuelo (día a día) sobre el saldo vencido.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

# Zona horaria canónica del proyecto (Argentina, sin DST → UTC-3 fijo).
_AR_TZ = timezone(timedelta(hours=-3))


# ─── Helpers de fechas / meses ────────────────────────────────────────────────

def today_ar() -> date:
    """Fecha de 'hoy' en horario de Argentina."""
    return datetime.now(_AR_TZ).date()


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    """Devuelve el primer día del mes resultante de sumar n meses a d."""
    total = (d.year * 12 + (d.month - 1)) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def months_between(a: date, b: date) -> int:
    """Cantidad de meses enteros de a → b (puede ser negativo)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def clamp_day(year: int, month: int, day: int) -> date:
    """date(year, month, day) recortando day al último día válido del mes."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last))


def due_date_for(contract, period: date) -> date:
    """Fecha de vencimiento del cobro de `period` según payment_due_day."""
    return clamp_day(period.year, period.month, contract.payment_due_day or 10)


# ─── Índice IPC ───────────────────────────────────────────────────────────────

def build_index_map(indices: List, code: str = "IPC") -> Dict[date, float]:
    """{ mes(primer día) : nivel } a partir de filas EconomicIndex del código dado."""
    out: Dict[date, float] = {}
    for ix in indices:
        if getattr(ix, "code", "IPC") != code:
            continue
        level = getattr(ix, "index_level", None)
        if level is None:
            continue
        out[month_start(ix.period)] = float(level)
    return out


def adjustment_cycles_elapsed(contract, period: date) -> int:
    """Cuántos ajustes ya ocurrieron entre el inicio del contrato y `period`."""
    freq = contract.adjustment_frequency_months or 0
    if freq <= 0:
        return 0
    months = months_between(month_start(contract.start_date), month_start(period))
    if months <= 0:
        return 0
    return months // freq


def compute_rent_for_period(
    contract, period: date, index_map: Optional[Dict[date, float]] = None
) -> Tuple[int, int, bool]:
    """
    Calcula el alquiler de un período.

    Devuelve (renta, monto_de_aumento, indice_pendiente):
      - renta: alquiler vigente para ese mes (entero).
      - monto_de_aumento: renta - base_rent (informativo).
      - indice_pendiente: True si falta cargar el IPC necesario (modo IPC).
    """
    base = contract.base_rent or 0
    cycles = adjustment_cycles_elapsed(contract, period)
    mode = contract.adjustment_index or "none"

    if cycles <= 0 or mode == "none":
        return base, 0, False

    if mode == "fixed":
        pct = contract.adjustment_fixed_pct or 0.0
        rent = round(base * ((1 + pct / 100.0) ** cycles))
        return rent, rent - base, False

    # IPC
    index_map = index_map or {}
    start_m = month_start(contract.start_date)
    boundary_m = add_months(start_m, cycles * (contract.adjustment_frequency_months or 0))
    l_start = index_map.get(start_m)
    l_boundary = index_map.get(boundary_m)
    if not l_start or not l_boundary:
        # Falta el índice: devolvemos la base y marcamos pendiente para que el panel avise.
        return base, 0, True
    rent = round(base * (l_boundary / l_start))
    return rent, rent - base, False


# ─── Gastos ───────────────────────────────────────────────────────────────────

def expenses_for_period(expenses: List, period: date) -> int:
    """Suma de gastos aplicables a `period` (recurrentes + los de ese mes puntual)."""
    total = 0
    pm = month_start(period)
    for e in expenses:
        if getattr(e, "recurring", False):
            total += e.amount or 0
        elif e.period and month_start(e.period) == pm:
            total += e.amount or 0
        # Gastos sin período ni recurrencia no se imputan a un mes automáticamente.
    return total


# ─── Punitorios (día a día) ───────────────────────────────────────────────────

def compute_punitorio(contract, due: Optional[date], outstanding: int, as_of: Optional[date] = None) -> int:
    """Punitorio acumulado sobre `outstanding` desde el vencimiento (+ gracia)."""
    if outstanding <= 0 or not due:
        return 0
    as_of = as_of or today_ar()
    grace = contract.grace_days or 0
    effective_due = due + timedelta(days=grace)
    days_late = (as_of - effective_due).days
    if days_late <= 0:
        return 0
    rate = (contract.punitorio_daily_pct or 0.0) / 100.0
    return round(outstanding * rate * days_late)


# ─── Figuras "en vivo" de un cobro ────────────────────────────────────────────

def live_charge_figures(charge, contract, expenses_amount: int, as_of: Optional[date] = None) -> dict:
    """
    Calcula las cifras a mostrar de un cobro.

    Para cobros pagados usa el snapshot guardado; para pendientes recalcula
    gastos, punitorios, total y el estado de visualización (incl. 'overdue').
    """
    as_of = as_of or today_ar()
    if charge.status == "paid":
        return {
            "expenses_amount": charge.expenses_amount or 0,
            "punitorio_amount": charge.punitorio_amount or 0,
            "total_amount": charge.total_amount or 0,
            "outstanding": 0,
            "display_status": "paid",
        }

    base = charge.base_amount or 0
    paid = charge.amount_paid or 0
    subtotal = base + (expenses_amount or 0)
    outstanding_before_punitorio = max(subtotal - paid, 0)
    punitorio = compute_punitorio(contract, charge.due_date, outstanding_before_punitorio, as_of)
    total = subtotal + punitorio
    outstanding = max(total - paid, 0)

    if charge.status == "cancelled":
        display = "cancelled"
    elif paid > 0 and outstanding > 0:
        display = "partial"
    elif charge.due_date and as_of > (charge.due_date + timedelta(days=contract.grace_days or 0)):
        display = "overdue"
    else:
        display = "pending"

    return {
        "expenses_amount": expenses_amount or 0,
        "punitorio_amount": punitorio,
        "total_amount": total,
        "outstanding": outstanding,
        "display_status": display,
    }


# ─── Generación idempotente de cuotas ─────────────────────────────────────────

def ensure_charges(db, contract, model_charge, expenses: Optional[List] = None,
                   index_map: Optional[Dict[date, float]] = None,
                   up_to: Optional[date] = None) -> int:
    """
    Crea las cuotas faltantes del contrato desde su inicio hasta `up_to`
    (por defecto, el mes actual). Idempotente: no duplica (UNIQUE contract+period).

    `model_charge` es la clase Charge (se inyecta para no acoplar el servicio al
    import del modelo). No hace commit — el llamador controla la transacción.

    Devuelve la cantidad de cuotas nuevas creadas.
    """
    if contract.status != "active":
        return 0
    up_to = month_start(up_to or today_ar())
    start = month_start(contract.start_date)
    end = month_start(contract.end_date) if contract.end_date else up_to
    last = min(up_to, end)
    if last < start:
        return 0

    existing = {month_start(c.period) for c in contract.charges} if contract.charges is not None else set()
    expenses = expenses if expenses is not None else list(getattr(contract, "expenses", []) or [])
    index_map = index_map or {}

    # tenant_id REQUIRED: RLS WITH CHECK rejects NULL on charges. A charge belongs to the
    # same agency (inmobiliaria) as its contract → contract.org_id. Fall back to the
    # resolver (default tenant) for legacy contracts whose org_id was never backfilled.
    from app.core.tenancy import resolve_tenant_id
    charge_tenant_id = getattr(contract, "org_id", None) or resolve_tenant_id()

    created = 0
    period = start
    while period <= last:
        if period not in existing:
            rent, adj, _pending = compute_rent_for_period(contract, period, index_map)
            exp = expenses_for_period(expenses, period)
            charge = model_charge(
                tenant_id=charge_tenant_id,
                contract_id=contract.id,
                period=period,
                due_date=due_date_for(contract, period),
                base_amount=rent,
                adjustment_amount=adj,
                expenses_amount=exp,
                punitorio_amount=0,
                total_amount=rent + exp,
                amount_paid=0,
                status="pending",
            )
            db.add(charge)
            created += 1
        period = add_months(period, 1)
    return created


# ─── Recordatorio de WhatsApp ─────────────────────────────────────────────────

def build_reminder_message(contract, charge, figures: dict, company_name: str = "",
                           tenant_name: str = "", currency: str = "ARS") -> str:
    """Arma el texto del recordatorio de pago para enviar por WhatsApp."""
    def money(n: int) -> str:
        prefix = "USD " if currency == "USD" else "$"
        return f"{prefix}{int(n):,.0f}".replace(",", ".")

    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    periodo = f"{meses[charge.period.month - 1]} {charge.period.year}"
    saludo = f"Hola {tenant_name}".strip() if tenant_name else "Hola"
    firma = f"\n\n{company_name}" if company_name else ""
    venc = charge.due_date.strftime("%d/%m/%Y") if charge.due_date else "—"

    lines = [
        f"{saludo}, te recordamos el pago del alquiler de {periodo}.",
        f"Vencimiento: {venc}",
        f"Alquiler: {money(charge.base_amount or 0)}",
    ]
    if figures.get("expenses_amount"):
        lines.append(f"Gastos/servicios: {money(figures['expenses_amount'])}")
    if figures.get("punitorio_amount"):
        lines.append(f"Punitorios: {money(figures['punitorio_amount'])}")
    lines.append(f"Total a pagar: {money(figures.get('total_amount', 0))}")
    return "\n".join(lines) + firma
