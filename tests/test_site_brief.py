"""Tests for the site-brief intake API (Profesional — "Mi sitio web", Fase A).

DB integration (skipped without Postgres): seeds a tenant + account, mints an access token,
and drives GET/PUT/submit through the real auth dependency to verify tenant scoping and
persistence. Auth context is set by ``get_current_account`` from the JWT.
"""
from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL / TEST_DATABASE_URL not set")


def _app():
    from fastapi import FastAPI
    from app.api.routes.site_brief import router

    app = FastAPI()
    app.include_router(router)
    return app


async def _seed_account():
    """Create a tenant + owner account; return (tenant_id, account_id, role)."""
    from app.db.models.tenant import Tenant
    from app.db.models.tenant_account import TenantAccount
    from app.db.session import async_session_factory

    tid = uuid4()
    aid = uuid4()
    async with async_session_factory() as s:
        s.add(Tenant(id=tid, slug=f"brief-{tid.hex[:8]}", display_name="Brief Test",
                     timezone="America/Argentina/Buenos_Aires", status="active"))
        s.add(TenantAccount(id=aid, tenant_id=tid,
                            email=f"brief-{aid.hex[:8]}@test.com", role="owner"))
        await s.commit()
    return tid, aid, "owner"


def _token(account_id, tenant_id, role) -> str:
    from app.core.security import create_access_token
    return create_access_token(account_id, tenant_id, role)


async def _client(token):
    app = _app()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t",
                             headers={"Authorization": f"Bearer {token}"})


@_db_skip
async def test_brief_requires_auth():
    app = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/site-brief")
    assert r.status_code == 401


@_db_skip
async def test_brief_get_empty_then_put_then_submit():
    tid, aid, role = await _seed_account()
    token = _token(aid, tid, role)

    async with await _client(token) as c:
        # Empty draft on first read.
        r = await c.get("/site-brief")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "draft"
        assert body["brand"] is None

        # Upsert a couple of sections.
        r = await c.put("/site-brief", json={
            "brand": {"brand_name": "Inmob Test", "colors": ["#0a0", "#fff"]},
            "domain": {"has_domain": False, "wants_us_to_buy": True},
            "design": {"style_direction": "minimalista", "notes": "limpio y claro"},
        })
        assert r.status_code == 200
        saved = r.json()
        assert saved["brand"]["brand_name"] == "Inmob Test"
        assert saved["domain"]["wants_us_to_buy"] is True

        # Persisted across requests.
        r = await c.get("/site-brief")
        assert r.json()["design"]["style_direction"] == "minimalista"

        # Submit flips status + timestamps.
        r = await c.post("/site-brief/submit")
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
        assert r.json()["submitted_at"] is not None


@_db_skip
async def test_brief_is_tenant_scoped():
    # Two tenants → each only sees its own brief.
    tid_a, aid_a, role = await _seed_account()
    tid_b, aid_b, _ = await _seed_account()

    async with await _client(_token(aid_a, tid_a, role)) as c:
        await c.put("/site-brief", json={"brand": {"brand_name": "Agency A"}})

    async with await _client(_token(aid_b, tid_b, role)) as c:
        r = await c.get("/site-brief")
        # Tenant B must NOT see Tenant A's brand.
        assert r.json()["brand"] is None
