"""Tests for the documents API (Enterprise — adjuntos a clientes/contratos).

DB integration (skipped without Postgres). Seeds a tenant + active subscription + account
+ a client, then drives upload/list/download/delete through the real auth dependency.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL / TEST_DATABASE_URL not set")

_HELLO_B64 = base64.b64encode(b"hello world pdf").decode()


def _app():
    from fastapi import FastAPI
    from app.api.routes.documents import router

    app = FastAPI()
    app.include_router(router)
    return app


def _token(account_id, tenant_id, role="owner") -> str:
    from app.core.security import create_access_token
    return create_access_token(account_id, tenant_id, role)


async def _seed():
    """tenant + active subscription + owner account + a client. Returns ids."""
    from app.core.tenancy import tenant_scope
    from app.db.models import Subscription, Tenant, TenantAccount, User
    from app.db.session import async_session_factory

    tid, aid, cid = uuid4(), uuid4(), uuid4()
    suffix = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with async_session_factory() as s:
        s.add(Tenant(id=tid, slug=f"doc-{suffix}", display_name="Doc Test", status="active"))
        await s.flush()  # tenant row must exist before the FK-bearing rows
        s.add(Subscription(id=uuid4(), tenant_id=tid, provider="mercadopago",
                           status="active", plan="Enterprise", currency="ARS",
                           current_period_end=now + timedelta(days=365)))
        s.add(TenantAccount(id=aid, tenant_id=tid, email=f"doc-{suffix}@test.com", role="owner"))
        await s.commit()
    # The client (user) must be inserted under the tenant's RLS scope.
    with tenant_scope(tid):
        async with async_session_factory() as s:
            s.add(User(id=cid, tenant_id=tid, name="Cliente Doc", whatsapp_phone=f"54{suffix}"))
            await s.commit()
    return {"tid": tid, "aid": aid, "cid": cid}


async def _client(token):
    transport = httpx.ASGITransport(app=_app())
    return httpx.AsyncClient(transport=transport, base_url="http://t",
                             headers={"Authorization": f"Bearer {token}"})


@_db_skip
async def test_upload_list_download_delete():
    d = await _seed()
    async with await _client(_token(d["aid"], d["tid"])) as c:
        # Upload
        r = await c.post("/documents", json={
            "client_id": str(d["cid"]), "category": "dni",
            "filename": "dni.pdf", "content_type": "application/pdf",
            "data": _HELLO_B64,
        })
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]
        assert r.json()["size_bytes"] == len(b"hello world pdf")

        # List by client
        r = await c.get("/documents", params={"client_id": str(d["cid"])})
        assert r.status_code == 200
        assert any(x["id"] == doc_id for x in r.json())

        # Download returns the original bytes
        r = await c.get(f"/documents/{doc_id}/download")
        assert r.status_code == 200
        assert r.content == b"hello world pdf"

        # Delete
        r = await c.delete(f"/documents/{doc_id}")
        assert r.status_code == 200
        r = await c.get("/documents", params={"client_id": str(d["cid"])})
        assert all(x["id"] != doc_id for x in r.json())


@_db_skip
async def test_rejects_no_target_and_bad_category():
    d = await _seed()
    async with await _client(_token(d["aid"], d["tid"])) as c:
        # No client nor contract
        r = await c.post("/documents", json={"category": "dni", "filename": "x.pdf",
                                             "content_type": "application/pdf", "data": _HELLO_B64})
        assert r.status_code == 422

        # Bad category
        r = await c.post("/documents", json={"client_id": str(d["cid"]), "category": "nope",
                                             "filename": "x.pdf", "content_type": "application/pdf",
                                             "data": _HELLO_B64})
        assert r.status_code == 422
