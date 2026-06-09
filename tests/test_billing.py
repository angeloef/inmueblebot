"""Billing/subscription tests (Phase 3 — MercadoPago).

Three layers:
  - Unit (offline): HMAC webhook-signature validation + pure gating logic.
  - ASGI integration (offline, no DB): webhook signature 403 / type routing /
    fail-closed-in-prod, exercised via ASGITransport with the sync step mocked.
  - DB integration (skipped without Postgres): state transitions + idempotency +
    trial expiry against a real ``subscriptions`` row.

Run unit-only:
    pytest tests/test_billing.py -k "signature or gating or webhook"

Run all (with Postgres):
    TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/test_billing.py
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from app.core import config

TEST_SECRET = "test-secret-key-32-chars-minimum-xx"
MP_WEBHOOK_SECRET = "mp-webhook-secret-abc123"

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(
    not _DB_URL,
    reason="DATABASE_URL / TEST_DATABASE_URL not set (Postgres required)",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("MERCADOPAGO_WEBHOOK_SECRET", MP_WEBHOOK_SECRET)
    monkeypatch.setenv("ENVIRONMENT", "development")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _dispose_db_engine() -> None:
    yield
    from app.db.session import async_session_factory

    bind = async_session_factory.kw.get("bind")
    if bind is not None:
        await bind.dispose()


def _signed_header(data_id: str, request_id: str, ts: str, secret: str) -> str:
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    h = hmac.new(secret.encode(), msg=manifest.encode(), digestmod=hashlib.sha256).hexdigest()
    return f"ts={ts},v1={h}"


# ---------------------------------------------------------------------------
# Unit: webhook signature validation
# ---------------------------------------------------------------------------

def test_signature_valid() -> None:
    from app.services.subscription_service import verify_webhook_signature

    data_id, req_id, ts = "12345", "req-abc", "1700000000"
    header = _signed_header(data_id, req_id, ts, MP_WEBHOOK_SECRET)
    assert verify_webhook_signature(header, req_id, data_id, MP_WEBHOOK_SECRET) is True


def test_signature_tampered_data_id() -> None:
    from app.services.subscription_service import verify_webhook_signature

    header = _signed_header("12345", "req-abc", "1700000000", MP_WEBHOOK_SECRET)
    # Attacker swaps the data.id but reuses the captured signature.
    assert verify_webhook_signature(header, "req-abc", "99999", MP_WEBHOOK_SECRET) is False


def test_signature_wrong_secret() -> None:
    from app.services.subscription_service import verify_webhook_signature

    header = _signed_header("12345", "req-abc", "1700000000", MP_WEBHOOK_SECRET)
    assert verify_webhook_signature(header, "req-abc", "12345", "other-secret") is False


def test_signature_missing_parts() -> None:
    from app.services.subscription_service import verify_webhook_signature

    assert verify_webhook_signature(None, "r", "1", MP_WEBHOOK_SECRET) is False
    assert verify_webhook_signature("ts=1", "r", "1", MP_WEBHOOK_SECRET) is False  # no v1
    assert verify_webhook_signature("v1=abc", "r", "1", MP_WEBHOOK_SECRET) is False  # no ts
    assert verify_webhook_signature("ts=1,v1=abc", "r", None, MP_WEBHOOK_SECRET) is False


# ---------------------------------------------------------------------------
# Unit: gating logic
# ---------------------------------------------------------------------------

class _FakeSub:
    def __init__(self, status: str, trial_ends_at: datetime | None) -> None:
        self.status = status
        self.trial_ends_at = trial_ends_at


def test_gating_active_grants_access() -> None:
    from app.services.subscription_service import subscription_grants_access

    assert subscription_grants_access(_FakeSub("active", None)) is True


def test_gating_trial_future_grants_access() -> None:
    from app.services.subscription_service import subscription_grants_access

    future = _utcnow() + timedelta(days=3)
    assert subscription_grants_access(_FakeSub("trial", future)) is True


def test_gating_trial_expired_blocks() -> None:
    from app.services.subscription_service import subscription_grants_access

    past = _utcnow() - timedelta(days=1)
    assert subscription_grants_access(_FakeSub("trial", past)) is False


def test_gating_paused_and_cancelled_block() -> None:
    from app.services.subscription_service import subscription_grants_access

    assert subscription_grants_access(_FakeSub("paused", None)) is False
    assert subscription_grants_access(_FakeSub("cancelled", None)) is False
    assert subscription_grants_access(_FakeSub("past_due", None)) is False
    assert subscription_grants_access(None) is False


# ---------------------------------------------------------------------------
# ASGI integration (no DB): webhook signature + routing + fail-closed
# ---------------------------------------------------------------------------

async def test_webhook_invalid_signature_403() -> None:
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhooks/mercadopago?data.id=12345&type=subscription_preapproval",
            headers={"x-signature": "ts=1700000000,v1=deadbeef", "x-request-id": "req-1"},
            json={"type": "subscription_preapproval", "data": {"id": "12345"}},
        )
        assert resp.status_code == 403, resp.text


async def test_webhook_valid_signature_triggers_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services import subscription_service

    called: dict[str, str] = {}

    async def _fake_sync(preapproval_id: str) -> bool:
        called["id"] = preapproval_id
        return True

    monkeypatch.setattr(subscription_service, "sync_from_preapproval_id", _fake_sync)

    data_id, req_id, ts = "preapp-777", "req-2", "1700000000"
    header = _signed_header(data_id, req_id, ts, MP_WEBHOOK_SECRET)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/webhooks/mercadopago?data.id={data_id}&type=subscription_preapproval",
            headers={"x-signature": header, "x-request-id": req_id},
            json={"type": "subscription_preapproval", "data": {"id": data_id}},
        )
        assert resp.status_code == 200, resp.text
        assert called.get("id") == data_id


async def test_webhook_non_subscription_type_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services import subscription_service

    called = {"hit": False}

    async def _fake_sync(preapproval_id: str) -> bool:
        called["hit"] = True
        return True

    monkeypatch.setattr(subscription_service, "sync_from_preapproval_id", _fake_sync)

    data_id, req_id, ts = "pay-1", "req-3", "1700000000"
    header = _signed_header(data_id, req_id, ts, MP_WEBHOOK_SECRET)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/webhooks/mercadopago?data.id={data_id}&type=payment",
            headers={"x-signature": header, "x-request-id": req_id},
            json={"type": "payment", "data": {"id": data_id}},
        )
        assert resp.status_code == 200, resp.text
        assert called["hit"] is False  # payment notifications are ignored here


async def test_webhook_fail_closed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """No webhook secret + ENVIRONMENT=production → reject (cannot validate)."""
    monkeypatch.delenv("MERCADOPAGO_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    config.get_settings.cache_clear()

    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/webhooks/mercadopago?data.id=1&type=subscription_preapproval",
            json={"data": {"id": "1"}},
        )
        assert resp.status_code == 403, resp.text


async def test_subscribe_requires_auth() -> None:
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/billing/subscribe")
        assert resp.status_code in (401, 403), resp.text


# ---------------------------------------------------------------------------
# Rate limiting on /billing/subscribe (per-tenant anti-abuse)
# ---------------------------------------------------------------------------

class _FakeAccount:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id


async def test_check_key_degrades_open_without_redis() -> None:
    """No Redis in the test env → check_key must allow (fail-open), never block."""
    from app.core.rate_limiter import rate_limiter

    assert await rate_limiter.check_key("test:key", 1, 60) is True


async def test_subscribe_rate_limit_blocks_with_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from app.api.routes import billing
    from app.core.rate_limiter import rate_limiter

    async def _over_limit(*_a: object, **_k: object) -> bool:
        return False

    monkeypatch.setattr(rate_limiter, "check_key", _over_limit)

    with pytest.raises(HTTPException) as exc:
        await billing._subscribe_rate_limit(account=_FakeAccount("t-1"))
    assert exc.value.status_code == 429
    assert exc.value.headers and "Retry-After" in exc.value.headers


async def test_subscribe_rate_limit_allows_within_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import billing
    from app.core.rate_limiter import rate_limiter

    async def _within_limit(*_a: object, **_k: object) -> bool:
        return True

    monkeypatch.setattr(rate_limiter, "check_key", _within_limit)

    account = _FakeAccount("t-2")
    returned = await billing._subscribe_rate_limit(account=account)
    assert returned is account


# ---------------------------------------------------------------------------
# DB integration: state transitions, idempotency, trial expiry
# ---------------------------------------------------------------------------

@_db_skip
async def test_sync_transitions_trial_to_active(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import select

    from app.db.models import Subscription, Tenant, TenantAccount
    from app.db.session import async_session_factory
    from app.services import auth_service, subscription_service

    account = await auth_service.signup(
        f"bill+{uuid4().hex[:8]}@example.com", "password123", "Billing Co"
    )
    tenant_id = account.tenant_id

    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        sub.mp_preapproval_id = "preapp-db-1"
        await session.commit()

    async def _fake_fetch(preapproval_id: str) -> dict:
        return {
            "id": preapproval_id,
            "status": "authorized",
            "payer_id": "payer-9",
            "external_reference": str(tenant_id),
            "next_payment_date": "2026-07-09T13:07:14.000-03:00",
        }

    monkeypatch.setattr(subscription_service, "_fetch_preapproval", _fake_fetch)

    # First sync → active.
    assert await subscription_service.sync_from_preapproval_id("preapp-db-1") is True
    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        tenant = await session.get(Tenant, tenant_id)
        assert sub.status == "active"
        assert sub.mp_payer_id == "payer-9"
        assert sub.current_period_end is not None
        assert tenant.status == "active"

    # Idempotent: second identical webhook → still active, no error.
    assert await subscription_service.sync_from_preapproval_id("preapp-db-1") is True
    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        assert sub.status == "active"

    # Cleanup.
    async with async_session_factory() as session:
        await session.delete(await session.get(Subscription, sub.id))
        await session.delete(await session.get(TenantAccount, account.id))
        await session.delete(await session.get(Tenant, tenant_id))
        await session.commit()


@_db_skip
async def test_mark_expired_trials() -> None:
    from sqlalchemy import select

    from app.db.models import Subscription, Tenant, TenantAccount
    from app.db.session import async_session_factory
    from app.services import auth_service, subscription_service

    account = await auth_service.signup(
        f"exp+{uuid4().hex[:8]}@example.com", "password123", "Expired Co"
    )
    tenant_id = account.tenant_id

    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        sub.trial_ends_at = _utcnow() - timedelta(days=1)  # already expired
        await session.commit()
        sub_id = sub.id

    changed = await subscription_service.mark_expired_trials()
    assert changed >= 1

    async with async_session_factory() as session:
        sub = await session.get(Subscription, sub_id)
        assert sub.status == "past_due"
        await session.delete(sub)
        await session.delete(await session.get(TenantAccount, account.id))
        await session.delete(await session.get(Tenant, tenant_id))
        await session.commit()
