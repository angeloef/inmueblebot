"""Tests for Enterprise multi-sucursal (Camino A: sucursal = sub-tenant + org-aware RLS).

DB integration (skipped without Postgres). Seeds an Enterprise org (parent tenant) with two
sucursales (child tenants) and a property in each, then verifies:
  - org-aware RLS: branch scope sees ONLY its rows; org scope sees ALL its branches' rows.
  - auth scoping: owner token consolidated vs. X-Branch-Id ("entrar a la sucursal"); a
    branch-manager token is hard-isolated to its branch.
  - cross-branch reassignment moves a property from one sucursal to another.
"""
from __future__ import annotations

import os
import random
from uuid import uuid4

import httpx
import pytest

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL / TEST_DATABASE_URL not set")


# ── Seeding ──────────────────────────────────────────────────────────────────


async def _seed_org_with_branches():
    """Create org (parent) + 2 branches + 1 property each. Returns ids + owner account."""
    from app.core.tenancy import tenant_scope
    from app.db.models.property import Property
    from app.db.models.tenant import Tenant
    from app.db.models.tenant_account import TenantAccount
    from app.db.session import async_session_factory

    org_id, a_id, b_id = uuid4(), uuid4(), uuid4()
    owner_id, mgr_a_id = uuid4(), uuid4()
    suffix = uuid4().hex[:8]

    async with async_session_factory() as s:
        s.add(Tenant(id=org_id, slug=f"org-{suffix}", display_name="Org Test", status="active"))
        s.add(Tenant(id=a_id, parent_tenant_id=org_id, slug=f"suc-a-{suffix}",
                     display_name="Sucursal A", status="active"))
        s.add(Tenant(id=b_id, parent_tenant_id=org_id, slug=f"suc-b-{suffix}",
                     display_name="Sucursal B", status="active"))
        # Owner login pinned to the ORG; branch manager pinned to Sucursal A.
        s.add(TenantAccount(id=owner_id, tenant_id=org_id,
                            email=f"owner-{suffix}@test.com", role="owner"))
        s.add(TenantAccount(id=mgr_a_id, tenant_id=a_id,
                            email=f"mgra-{suffix}@test.com", role="owner"))
        await s.commit()

    # Insert one property per branch UNDER that branch's RLS scope (WITH CHECK requires it).
    prop_a = random.randint(900_000_000, 999_999_999)
    prop_b = prop_a + 1
    for pid, tid, title in ((prop_a, a_id, "Casa A"), (prop_b, b_id, "Casa B")):
        with tenant_scope(tid):
            async with async_session_factory() as s:
                s.add(Property(id=pid, tenant_id=tid, title=title, price=1000,
                               type="alquiler", location="x", status="available"))
                await s.commit()

    return {
        "org_id": org_id, "a_id": a_id, "b_id": b_id,
        "owner_id": owner_id, "mgr_a_id": mgr_a_id,
        "prop_a": prop_a, "prop_b": prop_b,
    }


async def _property_tenant(prop_id):
    """Read a property's tenant_id directly (no RLS reliance — works as superuser)."""
    from sqlalchemy import text
    from app.db.session import async_session_factory

    async with async_session_factory() as s:
        return await s.scalar(
            text("SELECT tenant_id FROM properties WHERE id = :id"), {"id": prop_id}
        )


# ── Org-aware RLS (DB layer, via a NON-superuser role) ───────────────────────
# The docker test DB connects as ``postgres`` (a SUPERUSER), which BYPASSES RLS — so a
# raw count under a tenant GUC would see every row. To actually exercise the org-aware
# policy we spin up a throwaway non-superuser role, GRANT it SELECT, and probe via asyncpg.


async def _rls_probe_count(tenant_id) -> int:
    import os
    from urllib.parse import urlparse

    import asyncpg

    raw = (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or "")
    raw = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    p = urlparse(raw)
    host, port, db = p.hostname, p.port or 5432, (p.path or "/").lstrip("/")

    # As superuser: create the probe role + grants (idempotent).
    admin = await asyncpg.connect(host=host, port=port, database=db,
                                  user=p.username, password=p.password)
    try:
        # Drop dependent grants from a previous run before dropping the role.
        await admin.execute(
            "DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='rls_probe') "
            "THEN EXECUTE 'DROP OWNED BY rls_probe'; END IF; END $$;"
        )
        await admin.execute("DROP ROLE IF EXISTS rls_probe")
        await admin.execute("CREATE ROLE rls_probe LOGIN PASSWORD 'probe'")
        await admin.execute("GRANT USAGE ON SCHEMA public TO rls_probe")
        await admin.execute("GRANT SELECT ON properties, tenants TO rls_probe")
    finally:
        await admin.close()

    probe = await asyncpg.connect(host=host, port=port, database=db,
                                  user="rls_probe", password="probe")
    try:
        await probe.execute("SELECT set_config('app.current_tenant_id', $1, false)",
                            str(tenant_id))
        return await probe.fetchval("SELECT count(*) FROM properties")
    finally:
        await probe.close()


@_db_skip
async def test_branch_scope_is_isolated():
    d = await _seed_org_with_branches()
    # Under a non-superuser role, each branch GUC sees ONLY its own property.
    assert await _rls_probe_count(d["a_id"]) == 1
    assert await _rls_probe_count(d["b_id"]) == 1


@_db_skip
async def test_org_scope_sees_all_branches():
    d = await _seed_org_with_branches()
    # The org (parent) GUC sees BOTH branches' properties via the org-aware policy.
    assert await _rls_probe_count(d["org_id"]) == 2


# ── Auth scoping (HTTP layer) ────────────────────────────────────────────────


def _app():
    from fastapi import FastAPI
    from app.api.routes.auth import router as auth_router
    from app.api.routes.org import router as org_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(org_router)
    return app


def _token(account_id, tenant_id, role="owner") -> str:
    from app.core.security import create_access_token
    return create_access_token(account_id, tenant_id, role)


async def _client(token, headers=None):
    app = _app()
    h = {"Authorization": f"Bearer {token}"}
    if headers:
        h.update(headers)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t", headers=h)


@_db_skip
async def test_me_reports_org_scope_and_branches():
    d = await _seed_org_with_branches()
    async with await _client(_token(d["owner_id"], d["org_id"])) as c:
        r = await c.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "org"
    assert len(body["branches"]) == 2


@_db_skip
async def test_me_reports_branch_scope_for_manager():
    d = await _seed_org_with_branches()
    async with await _client(_token(d["mgr_a_id"], d["a_id"])) as c:
        r = await c.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["scope"] == "branch"


@_db_skip
async def test_branch_manager_cannot_use_org_routes():
    d = await _seed_org_with_branches()
    async with await _client(_token(d["mgr_a_id"], d["a_id"])) as c:
        r = await c.get("/org/branches")
    assert r.status_code == 403


@_db_skip
async def test_owner_branch_summary_consolidated():
    d = await _seed_org_with_branches()
    async with await _client(_token(d["owner_id"], d["org_id"])) as c:
        r = await c.get("/org/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["branch_count"] == 2
    assert len(body["branches"]) == 2
    # Exact per-branch counts depend on RLS (validated separately with a non-superuser
    # role); here we only assert the consolidated shape is well-formed.
    assert "properties" in body["totals"]
    assert isinstance(body["totals"]["properties"], int)


@_db_skip
async def test_reassign_property_between_branches():
    from app.api.routes.admin import router as admin_router
    from fastapi import FastAPI

    d = await _seed_org_with_branches()
    app = FastAPI()
    app.include_router(admin_router)
    transport = httpx.ASGITransport(app=app)
    token = _token(d["owner_id"], d["org_id"])
    async with httpx.AsyncClient(transport=transport, base_url="http://t",
                                 headers={"Authorization": f"Bearer {token}"}) as c:
        # Move Sucursal A's property to Sucursal B.
        r = await c.post(f"/admin/properties/{d['prop_a']}/reassign",
                         json={"branch_id": str(d["b_id"])})
        assert r.status_code == 200, r.text

    # The property now belongs to Sucursal B.
    assert await _property_tenant(d["prop_a"]) == d["b_id"]
