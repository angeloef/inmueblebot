"""Exportación de datos a CSV (Enterprise) — leads y cobranzas.

CSV con BOM UTF-8 (para que Excel muestre bien los acentos). Respeta el scope efectivo por
RLS: una sucursal exporta lo suyo; el dueño en consolidado exporta todas sus sucursales con
una columna ``sucursal``. Filtro opcional por rango de fechas.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text

from app.api.deps import require_plan
from app.db.models import TenantAccount
from app.db.session import async_session_factory

router = APIRouter(prefix="/exports", tags=["exports"])

_BOM = "﻿"


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Fecha inválida (YYYY-MM-DD)") from exc


def _csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for r in rows:
        writer.writerow(["" if v is None else v for v in r])
    body = _BOM + buf.getvalue()
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _date_bounds(date_from: str | None, date_to: str | None) -> tuple[datetime | None, datetime | None]:
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    start = datetime(d_from.year, d_from.month, d_from.day, tzinfo=timezone.utc) if d_from else None
    # inclusive 'to' → next day 00:00
    end = (datetime(d_to.year, d_to.month, d_to.day, tzinfo=timezone.utc) + timedelta(days=1)) if d_to else None
    return start, end


@router.get("/leads.csv")
async def export_leads(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    _: TenantAccount = Depends(require_plan(feature="exports")),  # noqa: B008
) -> Response:
    start, end = _date_bounds(date_from, date_to)
    where = []
    params: dict = {}
    if start is not None:
        where.append("u.created_at >= :start")
        params["start"] = start
    if end is not None:
        where.append("u.created_at < :end")
        params["end"] = end
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    sql = (
        "SELECT t.display_name AS sucursal, u.name, u.whatsapp_phone, "
        "u.extra_data->>'email' AS email, u.extra_data->>'role' AS rol, "
        "u.lead_score, u.budget_min, u.budget_max, u.created_at, u.last_interaction "
        "FROM users u LEFT JOIN tenants t ON t.id = u.tenant_id"
        f"{clause} ORDER BY u.created_at DESC"
    )
    async with async_session_factory() as s:
        rows = (await s.execute(text(sql), params)).all()

    header = ["Sucursal", "Nombre", "WhatsApp", "Email", "Rol", "Puntaje",
              "Presupuesto min", "Presupuesto max", "Fecha alta", "Última actividad"]
    return _csv_response("leads.csv", header, [list(r) for r in rows])


@router.get("/cobranzas.csv")
async def export_cobranzas(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    _: TenantAccount = Depends(require_plan(feature="exports")),  # noqa: B008
) -> Response:
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    where = []
    params: dict = {}
    if d_from is not None:
        where.append("c.due_date >= :dfrom")
        params["dfrom"] = d_from
    if d_to is not None:
        where.append("c.due_date <= :dto")
        params["dto"] = d_to
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    sql = (
        "SELECT t.display_name AS sucursal, u.name AS inquilino, p.title AS propiedad, "
        "c.period, c.base_amount, c.expenses_amount, c.total_amount, c.amount_paid, "
        "c.status, c.due_date, c.paid_at "
        "FROM charges c "
        "JOIN contracts ct ON ct.id = c.contract_id "
        "LEFT JOIN users u ON u.id = ct.tenant_id "
        "LEFT JOIN properties p ON p.id = ct.property_id "
        "LEFT JOIN tenants t ON t.id = c.tenant_id"
        f"{clause} ORDER BY c.due_date DESC NULLS LAST"
    )
    async with async_session_factory() as s:
        rows = (await s.execute(text(sql), params)).all()

    header = ["Sucursal", "Inquilino", "Propiedad", "Período", "Alquiler base",
              "Gastos", "Total", "Pagado", "Estado", "Vencimiento", "Fecha de pago"]
    return _csv_response("cobranzas.csv", header, [list(r) for r in rows])
