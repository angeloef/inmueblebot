"""Tests for CSV exports (Enterprise) — leads + cobranzas.

DB integration (skipped without Postgres). Seeds a tenant + active subscription + account
+ a lead, then verifies the CSV endpoints return well-formed CSV (BOM + header + rows).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL / TEST_DATABASE_URL not set")


async def _seed():
    from app.core.tenancy import tenant_scope
    from app.db.models import Subscription, Tenant, TenantAccount, User
    from app.db.session import async_session_factory

    tid, aid = uuid4(), uuid4()
    suffix = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    async with async_session_factory() as s:
        s.add(Tenant(id=tid, slug=f"exp-{suffix}", display_name="Export Test", status="active"))
        await s.flush()
        s.add(Subscription(id=uuid4(), tenant_id=tid, provider="mercadopago",
                           status="active", plan="Enterprise", currency="ARS",
                           current_period_end=now + timedelta(days=365)))
        s.add(TenantAccount(id=aid, tenant_id=tid, email=f"exp-{suffix}@test.com", role="owner"))
        await s.commit()
    with tenant_scope(tid):
        async with async_session_factory() as s:
            s.add(User(id=uuid4(), tenant_id=tid, name="Lead Export",
                       whatsapp_phone=f"54{suffix}", extra_data={"email": "lead@x.com", "role": "prospect"}))
            await s.commit()
    return {"tid": tid, "aid": aid, "suffix": suffix}


def _token(account_id, tenant_id, role="owner"):
    from app.core.security import create_access_token
    return create_access_token(account_id, tenant_id, role)


def _app():
    from fastapi import FastAPI
    from app.api.routes.exports import router
    app = FastAPI()
    app.include_router(router)
    return app


async def _client(token):
    transport = httpx.ASGITransport(app=_app())
    return httpx.AsyncClient(transport=transport, base_url="http://t",
                             headers={"Authorization": f"Bearer {token}"})


@_db_skip
async def test_leads_csv_has_bom_header_and_row():
    d = await _seed()
    async with await _client(_token(d["aid"], d["tid"])) as c:
        r = await c.get("/exports/leads.csv")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    body = r.text
    assert body.startswith("﻿")  # BOM
    assert "Nombre" in body and "WhatsApp" in body  # header
    assert "Lead Export" in body  # the seeded lead


@_db_skip
async def test_cobranzas_csv_header_ok():
    d = await _seed()
    async with await _client(_token(d["aid"], d["tid"])) as c:
        r = await c.get("/exports/cobranzas.csv")
    assert r.status_code == 200, r.text
    body = r.text
    assert body.startswith("﻿")
    assert "Inquilino" in body and "Vencimiento" in body


@_db_skip
async def test_date_filter_accepts_range():
    d = await _seed()
    async with await _client(_token(d["aid"], d["tid"])) as c:
        r = await c.get("/exports/leads.csv", params={"from": "2020-01-01", "to": "2020-01-02"})
    assert r.status_code == 200
    # Out-of-range → header only (the seeded lead is from today).
    assert "Lead Export" not in r.text
