"""Cálculo de métricas ejecutivas Enterprise (embudo / cobranzas / cartera / demanda).

Una sola función ``compute_metrics`` que corre bajo el RLS de un tenant (sucursal) y
devuelve los 4 grupos de KPIs para un mes. La reusan: la vista Reportes del dashboard, el
job de snapshot mensual y el job de reporte ejecutivo por WhatsApp.

Métricas con dimensión temporal (embudo, actividad de cobranzas del mes) se filtran por el
rango [period_start, period_end). Las de estado (cartera, demanda, morosidad) son foto al
momento de cálculo (``today``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text

from app.core.tenancy import tenant_scope
from app.db.session import async_session_factory

# Contrato por vencer = vence dentro de esta ventana.
EXPIRING_WINDOW_DAYS = 60


def _rate(num: float, den: float) -> float:
    return round((num / den) * 100, 1) if den else 0.0


async def compute_metrics(
    tenant_id: UUID,
    period_start: date,
    period_end: date,
    today: date | None = None,
) -> dict:
    """Compute the 4 metric groups for ``tenant_id`` over [period_start, period_end)."""
    today = today or datetime.now(timezone.utc).date()  # noqa: UP017
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)

    with tenant_scope(tenant_id):
        async with async_session_factory() as s:
            async def scalar(sql: str, **params) -> float:
                params.setdefault("start", start_dt)
                params.setdefault("end", end_dt)
                params.setdefault("today", today)
                params.setdefault("month", period_start)
                v = await s.scalar(text(sql), params)
                return v or 0

            # ── Embudo + conversión (rango temporal) ─────────────────────────
            leads = await scalar("SELECT count(*) FROM users WHERE created_at >= :start AND created_at < :end")
            conversations = await scalar(
                "SELECT count(*) FROM conversations WHERE created_at >= :start AND created_at < :end")
            visits_scheduled = await scalar(
                "SELECT count(*) FROM appointments WHERE type = 'visit' "
                "AND created_at >= :start AND created_at < :end")
            visits_done = await scalar(
                "SELECT count(*) FROM appointments WHERE status = 'completed' "
                "AND start_time >= :start AND start_time < :end")
            no_show = await scalar(
                "SELECT count(*) FROM appointments WHERE status = 'no_show' "
                "AND start_time >= :start AND start_time < :end")
            closings = await scalar(
                "SELECT count(*) FROM properties WHERE status IN ('sold','rented') "
                "AND updated_at >= :start AND updated_at < :end")

            funnel = {
                "leads": int(leads),
                "conversations": int(conversations),
                "visits_scheduled": int(visits_scheduled),
                "visits_done": int(visits_done),
                "no_show": int(no_show),
                "closings": int(closings),
                "rates": {
                    "lead_to_visit": _rate(visits_scheduled, leads),
                    "show_rate": _rate(visits_done, visits_done + no_show),
                    "visit_to_close": _rate(closings, visits_done),
                },
            }

            # ── Cobranzas / financiero ───────────────────────────────────────
            billed = await scalar(
                "SELECT coalesce(sum(base_amount + expenses_amount),0) FROM charges WHERE period = :month")
            paid = await scalar(
                "SELECT coalesce(sum(amount_paid),0) FROM charges WHERE period = :month")
            charges_total = await scalar("SELECT count(*) FROM charges WHERE period = :month")
            charges_paid = await scalar(
                "SELECT count(*) FROM charges WHERE period = :month AND status = 'paid'")
            overdue_count = await scalar(
                "SELECT count(*) FROM charges WHERE status IN ('pending','partial') AND due_date < :today")
            morosidad = await scalar(
                "SELECT coalesce(sum(base_amount + expenses_amount - amount_paid),0) FROM charges "
                "WHERE status IN ('pending','partial') AND due_date < :today")
            expiring = await scalar(
                "SELECT count(*) FROM contracts WHERE status = 'active' "
                "AND end_date IS NOT NULL AND end_date BETWEEN :today AND :exp",
                exp=today + timedelta(days=EXPIRING_WINDOW_DAYS))

            cobranzas = {
                "billed": int(billed),
                "paid": int(paid),
                "pct_cobrado": _rate(charges_paid, charges_total),
                "overdue_count": int(overdue_count),
                "morosidad_amount": int(morosidad),
                "contracts_expiring": int(expiring),
            }

            # ── Cartera (foto actual) ────────────────────────────────────────
            available = await scalar("SELECT count(*) FROM properties WHERE status = 'available'")
            reserved = await scalar("SELECT count(*) FROM properties WHERE status = 'reserved'")
            closed = await scalar("SELECT count(*) FROM properties WHERE status IN ('sold','rented')")
            dead = await scalar(
                "SELECT count(*) FROM properties p WHERE p.status = 'available' "
                "AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.property_id = p.id)")
            avg_age = await scalar(
                "SELECT coalesce(avg(EXTRACT(EPOCH FROM (now() - created_at)) / 86400), 0) "
                "FROM properties WHERE status = 'available'")

            cartera = {
                "available": int(available),
                "reserved": int(reserved),
                "closed": int(closed),
                "dead": int(dead),
                "avg_age_days": round(float(avg_age), 1),
            }

            # ── Demanda de mercado (foto actual) ─────────────────────────────
            top_zones = (await s.execute(text(
                "SELECT zone_name, search_count, property_count FROM zone_stats "
                "ORDER BY search_count DESC LIMIT 5"))).all()
            gaps = (await s.execute(text(
                "SELECT zone_name, search_count FROM zone_stats "
                "WHERE property_count = 0 AND search_count > 0 ORDER BY search_count DESC LIMIT 5"))).all()
            failures = (await s.execute(text(
                "SELECT operation, property_type, zone, fail_count FROM search_failures "
                "ORDER BY fail_count DESC LIMIT 5"))).all()

            demanda = {
                "top_zones": [
                    {"zone": z, "searches": int(sc or 0), "inventory": int(pc or 0)}
                    for (z, sc, pc) in top_zones
                ],
                "supply_gaps": [
                    {"zone": z, "searches": int(sc or 0)} for (z, sc) in gaps
                ],
                "dead_end_searches": [
                    {"operation": op, "type": pt, "zone": z, "count": int(fc or 0)}
                    for (op, pt, z, fc) in failures
                ],
            }

    return {"funnel": funnel, "cobranzas": cobranzas, "cartera": cartera, "demanda": demanda}
