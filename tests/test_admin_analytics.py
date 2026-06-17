"""Tests de la analítica de plataforma super-admin (plan 06).

Offline (sin DB): el gate de auth (401 sin credenciales) y los helpers puros de
series temporales y narrativa determinística. La agregación cross-tenant real (RLS) se
apoya en el mismo escape hatch que cubre ``test_superadmin_cross_tenant.py`` (plan 04);
acá probamos la capa de endpoint y la lógica determinística sin tocar Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.api.deps import require_superadmin
from app.api.routes.admin_analytics import (
    _TREND_MONTHS,
    _month_key,
    _recent_months,
    _saas_narrative,
)


# ── Helpers puros ────────────────────────────────────────────────────────────


def test_month_key_formats_and_handles_none() -> None:
    assert _month_key(datetime(2026, 5, 9, tzinfo=timezone.utc)) == "2026-05"
    assert _month_key(None) is None


def test_recent_months_is_ascending_and_sized() -> None:
    months = _recent_months(_TREND_MONTHS)
    assert len(months) == _TREND_MONTHS
    # Orden ascendente y termina en el mes actual.
    assert months == sorted(months)
    now = datetime.now(timezone.utc)
    assert months[-1] == f"{now.year:04d}-{now.month:02d}"


def test_recent_months_crosses_year_boundary() -> None:
    # 3 meses pedidos siempre dan 3 claves válidas 'YYYY-MM' sin huecos.
    months = _recent_months(3)
    assert len(months) == 3
    for m in months:
        year, month = m.split("-")
        assert 1 <= int(month) <= 12
        assert len(year) == 4


def test_saas_narrative_summarizes_state() -> None:
    saas = {
        "total_tenants": 3,
        "tenants_by_status": {"active": 2, "trial": 1},
        "mrr_by_currency": {"ARS": 30000.0},
        "signups_by_month": [{"month": "2026-05", "count": 1}, {"month": "2026-06", "count": 2}],
        "churn_by_month": [],
    }
    usage = {"properties": 10, "appointments": 4, "conversations": 8, "messages": 99}
    text = _saas_narrative(saas, usage)
    assert "3 inmobiliarias" in text
    assert "2 activas" in text
    assert "ARS" in text
    # Altas "este mes" usan el último mes de la serie (count=2).
    assert "Altas este mes: 2" in text


def test_saas_narrative_handles_no_revenue() -> None:
    saas = {
        "total_tenants": 1,
        "tenants_by_status": {"trial": 1},
        "mrr_by_currency": {},
        "signups_by_month": [],
        "churn_by_month": [],
    }
    usage = {"properties": 0, "appointments": 0, "conversations": 0, "messages": 0}
    text = _saas_narrative(saas, usage)
    assert "sin ingresos activos" in text
    assert "Altas este mes: 0" in text


# ── Endpoint: auth gate (offline) ────────────────────────────────────────────


async def _client() -> httpx.AsyncClient:
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_overview_requires_auth() -> None:
    """Sin credenciales ⇒ 401 antes de tocar la DB (fail-closed)."""
    async with await _client() as client:
        resp = await client.get("/admin/analytics/overview")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tenants_requires_auth() -> None:
    async with await _client() as client:
        resp = await client.get("/admin/analytics/tenants")
    assert resp.status_code == 401
