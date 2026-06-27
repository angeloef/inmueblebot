"""Analítica de plataforma cross-tenant para la consola super-admin (plan 06).

Endpoints ``/admin/analytics/*`` que agregan datos de **todas** las inmobiliarias en
una sola request: negocio/SaaS, uso de producto, salud técnica/ops y drilldown por
tenant. El acceso cross-tenant lo habilita el GUC ``app.is_superadmin`` que setea
``require_superadmin`` (plan 04): dentro de la request, RLS expone filas de cualquier
tenant. ``subscriptions`` es global (sin RLS), el resto se ve por el GUC.

Diseño:
  - **No recalcula** lo que ya existe: cuenta con agregaciones SQL baratas (``GROUP BY``),
    no trae filas a Python salvo para el merge del drilldown.
  - **Determinístico**: el resumen narrativo se arma con plantillas (sin LLM/costo).
  - **Sin inventar datos**: las métricas de ops (latencia/costos IA) no tienen fuente
    persistida ⇒ se devuelven marcadas ``phase2`` en vez de fabricarlas.
  - **Fail-closed**: todo cuelga de ``require_superadmin`` ⇒ no-superadmin → 401/403.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import require_superadmin
from app.api.routes.admin import _make_async_session

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])

# Estados de suscripción que cuentan como ingreso recurrente vivo.
_ACTIVE_SUB_STATUSES = ("active",)
# Cuántos meses de historia incluir en las series temporales (altas/bajas).
_TREND_MONTHS = 6


def _month_key(dt: datetime | None) -> str | None:
    """``datetime`` → ``'YYYY-MM'`` (clave de mes estable para series)."""
    return dt.strftime("%Y-%m") if dt is not None else None


def _recent_months(n: int) -> list[str]:
    """Últimos ``n`` meses como ``'YYYY-MM'`` ascendente, terminando en el mes actual."""
    now = datetime.now(UTC)
    keys: list[str] = []
    year, month = now.year, now.month
    for _ in range(n):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(keys))


async def _tenant_name_map(db) -> dict[str, str]:  # noqa: ANN001
    """id(str) → nombre legible de la inmobiliaria.

    Proyecta solo las columnas necesarias (no ``select(Tenant)``) para no traer a memoria
    columnas sensibles del tenant (tokens/credenciales) que nunca se devuelven.
    """
    from app.db.models.tenant import Tenant

    rows = (
        await db.execute(
            select(Tenant.id, Tenant.display_name, Tenant.company_name, Tenant.slug)
        )
    ).all()
    return {
        str(tid): (display_name or company_name or slug or str(tid))
        for tid, display_name, company_name, slug in rows
    }


def _trend_cutoff() -> datetime:
    """Inicio de la ventana de tendencia: primer día del mes ``_TREND_MONTHS-1`` atrás.

    Acota las queries de altas/bajas a la ventana que se reporta, en vez de traer todas
    las filas históricas a memoria (la serie de salida ya se recorta a ``_TREND_MONTHS``).
    """
    now = datetime.now(UTC)
    # Margen holgado de 31 días/mes; el conteo final filtra por clave 'YYYY-MM' igual.
    return (now - timedelta(days=31 * _TREND_MONTHS)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )


async def _count_all(db, model) -> int:  # noqa: ANN001
    """Total de filas de un modelo (cross-tenant vía RLS superadmin)."""
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _count_by_tenant(db, model) -> dict[str, int]:  # noqa: ANN001
    """``{tenant_id(str): count}`` para un modelo con columna ``tenant_id``."""
    rows = (
        await db.execute(
            select(model.tenant_id, func.count())
            .group_by(model.tenant_id)
        )
    ).all()
    return {str(tid): cnt for tid, cnt in rows if tid is not None}


def _saas_narrative(saas: dict, usage: dict) -> str:
    """Resumen narrativo determinístico del estado de la plataforma."""
    active = saas["tenants_by_status"].get("active", 0)
    trial = saas["tenants_by_status"].get("trial", 0)
    total = saas["total_tenants"]
    mrr_parts = [f"{cur} {amt:,.0f}" for cur, amt in sorted(saas["mrr_by_currency"].items())]
    mrr_txt = " + ".join(mrr_parts) if mrr_parts else "sin ingresos activos"
    signups = saas["signups_by_month"]
    last_month = signups[-1]["count"] if signups else 0
    return (
        f"{total} inmobiliarias en la plataforma ({active} activas, {trial} en trial). "
        f"MRR: {mrr_txt}. Altas este mes: {last_month}. "
        f"Uso acumulado: {usage['properties']} propiedades, {usage['appointments']} citas, "
        f"{usage['conversations']} conversaciones."
    )


@router.get("/overview")
async def analytics_overview(
    _: object = Depends(require_superadmin),
) -> dict:
    """Agregados a nivel plataforma: SaaS/negocio, uso de producto, ops y narrativa."""
    from app.db.models import (
        Appointment,
        Conversation,
        Message,
        Property,
        Subscription,
        Tenant,
    )

    async with _make_async_session() as db:
        # ── SaaS / negocio ──────────────────────────────────────────────────
        total_tenants = (await db.execute(select(func.count()).select_from(Tenant))).scalar_one()

        sub_status_rows = (
            await db.execute(
                select(Subscription.status, func.count()).group_by(Subscription.status)
            )
        ).all()
        tenants_by_status = dict(sub_status_rows)

        mrr_rows = (
            await db.execute(
                select(Subscription.currency, func.coalesce(func.sum(Subscription.amount), 0))
                .where(Subscription.status.in_(_ACTIVE_SUB_STATUSES))
                .group_by(Subscription.currency)
            )
        ).all()
        mrr_by_currency = {cur: float(amt) for cur, amt in mrr_rows}

        # Altas por mes (tenants.created_at) y bajas por mes (subs cancelled.updated_at),
        # acotadas a la ventana reportada para no traer todo el histórico a memoria.
        cutoff = _trend_cutoff()
        signup_rows = (
            await db.execute(select(Tenant.created_at).where(Tenant.created_at >= cutoff))
        ).scalars().all()
        signup_counts: dict[str, int] = defaultdict(int)
        for dt in signup_rows:
            key = _month_key(dt)
            if key:
                signup_counts[key] += 1

        churn_rows = (
            await db.execute(
                select(Subscription.updated_at).where(
                    Subscription.status == "cancelled",
                    Subscription.updated_at >= cutoff,
                )
            )
        ).scalars().all()
        churn_counts: dict[str, int] = defaultdict(int)
        for dt in churn_rows:
            key = _month_key(dt)
            if key:
                churn_counts[key] += 1

        months = _recent_months(_TREND_MONTHS)
        signups_by_month = [{"month": m, "count": signup_counts.get(m, 0)} for m in months]
        churn_by_month = [{"month": m, "count": churn_counts.get(m, 0)} for m in months]

        # ── Uso de producto ─────────────────────────────────────────────────
        usage = {
            "properties": await _count_all(db, Property),
            "appointments": await _count_all(db, Appointment),
            "messages": await _count_all(db, Message),
            "conversations": await _count_all(db, Conversation),
        }
        # Conversión grosera: citas agendadas sobre conversaciones iniciadas.
        convs = usage["conversations"] or 0
        usage["conversion_rate"] = round(usage["appointments"] / convs, 4) if convs else None

        saas = {
            "total_tenants": total_tenants,
            "tenants_by_status": tenants_by_status,
            "mrr_by_currency": mrr_by_currency,
            "signups_by_month": signups_by_month,
            "churn_by_month": churn_by_month,
        }

    # ── Ops / salud técnica: sin fuente persistida ⇒ fase 2 (no inventar) ───
    ops = {
        "phase2": True,
        "note": "Latencia, errores y costos de IA aún no se persisten como métrica. "
        "Disponible en fase 2.",
    }

    return {
        "saas": saas,
        "usage": usage,
        "ops": ops,
        "narrative": _saas_narrative(saas, usage),
    }


@router.get("/tenants")
async def analytics_tenants(
    _: object = Depends(require_superadmin),
) -> dict:
    """Drilldown: una fila por tenant con sus KPIs de uso y estado de suscripción."""
    from app.db.models import (
        Appointment,
        Conversation,
        Message,
        Property,
        Subscription,
    )

    async with _make_async_session() as db:
        names = await _tenant_name_map(db)
        props = await _count_by_tenant(db, Property)
        appts = await _count_by_tenant(db, Appointment)
        msgs = await _count_by_tenant(db, Message)
        convs = await _count_by_tenant(db, Conversation)

        sub_rows = (
            await db.execute(
                select(Subscription.tenant_id, Subscription.status, Subscription.plan,
                       Subscription.amount, Subscription.currency)
            )
        ).all()
        subs = {
            str(tid): {
                "status": status,
                "plan": plan,
                "amount": float(amount) if amount is not None else None,
                "currency": currency,
            }
            for tid, status, plan, amount, currency in sub_rows
        }

    items = []
    for tid, name in names.items():
        conversations = convs.get(tid, 0)
        appointments = appts.get(tid, 0)
        sub = subs.get(tid, {})
        items.append({
            "tenant_id": tid,
            "tenant_name": name,
            "properties": props.get(tid, 0),
            "appointments": appointments,
            "messages": msgs.get(tid, 0),
            "conversations": conversations,
            "conversion_rate": round(appointments / conversations, 4) if conversations else None,
            "subscription_status": sub.get("status"),
            "plan": sub.get("plan"),
            "mrr_amount": sub.get("amount") if sub.get("status") in _ACTIVE_SUB_STATUSES else None,
            "currency": sub.get("currency"),
        })

    # Orden por uso descendente (más activos primero) — el más relevante para los devs.
    items.sort(key=lambda r: (r["properties"] + r["appointments"]), reverse=True)
    return {"items": items, "total": len(items)}
