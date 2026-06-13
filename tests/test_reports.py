"""Tests for Enterprise executive reports (métricas + snapshot mensual).

DB integration (skipped without Postgres). Seeds an org + 2 branches (with a property each)
+ active subscription, then verifies the /reports route (consolidated vs branch) and the
monthly snapshot job.
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL / TEST_DATABASE_URL not set")


async def _seed():
    from app.core.tenancy import tenant_scope
    from app.db.models import Subscription, Tenant, TenantAccount
    from app.db.models.property import Property
    from app.db.session import async_session_factory

    org_id, a_id, b_id = uuid4(), uuid4(), uuid4()
    owner_id, mgr_a_id = uuid4(), uuid4()
    suffix = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with async_session_factory() as s:
        s.add(Tenant(id=org_id, slug=f"rep-{suffix}", display_name="Rep Org", status="active"))
        await s.flush()
        s.add(Tenant(id=a_id, parent_tenant_id=org_id, slug=f"rep-a-{suffix}",
                     display_name="Sucursal A", status="active"))
        s.add(Tenant(id=b_id, parent_tenant_id=org_id, slug=f"rep-b-{suffix}",
                     display_name="Sucursal B", status="active"))
        s.add(Subscription(id=uuid4(), tenant_id=org_id, provider="mercadopago",
                           status="active", plan="Enterprise", currency="ARS",
                           current_period_end=now + timedelta(days=365)))
        s.add(TenantAccount(id=owner_id, tenant_id=org_id, email=f"ro-{suffix}@test.com", role="owner"))
        s.add(TenantAccount(id=mgr_a_id, tenant_id=a_id, email=f"rma-{suffix}@test.com", role="owner"))
        await s.commit()

    for tid in (a_id, b_id):
        with tenant_scope(tid):
            async with async_session_factory() as s:
                s.add(Property(id=random.randint(600_000_000, 699_999_999), tenant_id=tid,
                               title="Prop", price=1000, type="alquiler", location="x",
                               status="available"))
                await s.commit()
    return {"org_id": org_id, "a_id": a_id, "b_id": b_id,
            "owner_id": owner_id, "mgr_a_id": mgr_a_id}


def _token(account_id, tenant_id, role="owner"):
    from app.core.security import create_access_token
    return create_access_token(account_id, tenant_id, role)


def _app():
    from fastapi import FastAPI
    from app.api.routes.reports import router
    app = FastAPI()
    app.include_router(router)
    return app


async def _client(token):
    transport = httpx.ASGITransport(app=_app())
    return httpx.AsyncClient(transport=transport, base_url="http://t",
                             headers={"Authorization": f"Bearer {token}"})


@_db_skip
async def test_org_report_is_consolidated_with_branches():
    d = await _seed()
    async with await _client(_token(d["owner_id"], d["org_id"])) as c:
        r = await c.get("/reports")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "org"
    assert len(body["branches"]) == 2
    # The 4 metric groups must be present in the totals.
    for group in ("funnel", "cobranzas", "cartera", "demanda"):
        assert group in body["totals"]
    # Org totals see both branches' available properties (org-aware RLS).
    assert body["totals"]["cartera"]["available"] >= 2


@_db_skip
async def test_branch_manager_report_is_single():
    d = await _seed()
    async with await _client(_token(d["mgr_a_id"], d["a_id"])) as c:
        r = await c.get("/reports")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "branch"
    # Exact RLS-scoped counts are validated separately (non-superuser probe in
    # test_multisucursal); here we assert the single-tenant report shape.
    for group in ("funnel", "cobranzas", "cartera", "demanda"):
        assert group in body["metrics"]
    assert "prev" in body


@_db_skip
async def test_periods_endpoint():
    d = await _seed()
    async with await _client(_token(d["owner_id"], d["org_id"])) as c:
        r = await c.get("/reports/periods")
    assert r.status_code == 200
    periods = r.json()["periods"]
    assert len(periods) == 12
    assert periods[0]["is_current"] is True


@_db_skip
async def test_monthly_snapshot_job_persists_a_row():
    from sqlalchemy import text
    from app.core.tenancy import tenant_scope
    from app.db.session import async_session_factory
    from app.services.jobs import monthly_snapshot

    d = await _seed()
    # Snapshot just one branch (avoid iterating the whole polluted DB).
    await monthly_snapshot._per_tenant(d["a_id"])

    with tenant_scope(d["a_id"]):
        async with async_session_factory() as s:
            count = await s.scalar(
                text("SELECT count(*) FROM metric_snapshots WHERE tenant_id = :t"),
                {"t": str(d["a_id"])},
            )
    assert count == 1
