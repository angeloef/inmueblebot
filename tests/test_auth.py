"""Auth unit + integration tests (Phase 1 JWT multi-tenant).

Unit tests run offline (no DB/Redis). DB integration tests are skipped unless
DATABASE_URL or TEST_DATABASE_URL is set to a real Postgres instance.

Run unit-only:
    pytest tests/test_auth.py -k "unit"

Run all (with Postgres):
    TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/test_auth.py
"""
from __future__ import annotations

import os
from uuid import uuid4

import httpx
import jwt
import pytest

from app.core import config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-key-32-chars-minimum-xx"

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(
    not _DB_URL,
    reason="DATABASE_URL / TEST_DATABASE_URL not set (Postgres required)",
)


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _dispose_db_engine() -> None:
    """Dispose the module-level async engine's pool after each test.

    ``async_session_factory`` is a process-wide singleton bound to one engine.
    Under ``asyncio_mode=auto`` every test runs in its own event loop, so a
    connection created in test A's loop and reused in test B's loop raises
    "attached to a different loop". Disposing after each test (in that test's
    own loop) guarantees the next test opens fresh connections on its own loop.
    """
    yield
    from app.db.session import async_session_factory

    bind = async_session_factory.kw.get("bind")
    if bind is not None:
        await bind.dispose()


# ---------------------------------------------------------------------------
# Unit: password hashing
# ---------------------------------------------------------------------------

def test_password_hash_roundtrip() -> None:
    from app.core.security import hash_password, verify_password

    plain = "supersecret42"
    hashed = hash_password(plain)
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong", hashed) is False


# ---------------------------------------------------------------------------
# Unit: JWT roundtrip and claims
# ---------------------------------------------------------------------------

def test_jwt_roundtrip_and_claims() -> None:
    from app.core.security import create_access_token, decode_token

    acc_id = uuid4()
    tid = uuid4()
    token = create_access_token(acc_id, tid, "owner")
    payload = decode_token(token)

    assert payload["sub"] == str(acc_id)
    assert payload["tid"] == str(tid)
    assert payload["role"] == "owner"
    assert payload["type"] == "access"


def test_jwt_type_mismatch() -> None:
    from app.core.security import create_refresh_token, decode_token

    token = create_refresh_token(uuid4(), uuid4(), "owner")
    payload = decode_token(token)
    assert payload["type"] == "refresh"


def test_jwt_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.security import create_access_token, decode_token

    monkeypatch.setenv("ACCESS_TOKEN_TTL_MIN", "-1")
    config.get_settings.cache_clear()

    token = create_access_token(uuid4(), uuid4(), "owner")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


# ---------------------------------------------------------------------------
# DB integration: signup, login, refresh, duplicate, /me
# ---------------------------------------------------------------------------

@_db_skip
async def test_signup_then_login() -> None:
    from app.main import app

    email = f"test+{uuid4().hex[:8]}@example.com"
    password = "password123"
    agency = "Test Agency"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/auth/signup",
            json={"email": email, "password": password, "agency_name": agency},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

        resp2 = await client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert resp2.status_code == 200, resp2.text
        assert "access_token" in resp2.json()


@_db_skip
async def test_login_wrong_password() -> None:
    from app.main import app

    email = f"test+{uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/auth/signup",
            json={"email": email, "password": "correct-pass", "agency_name": "Agencia"},
        )
        resp = await client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-pass"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"


@_db_skip
async def test_signup_duplicate_email() -> None:
    from app.main import app

    email = f"dup+{uuid4().hex[:8]}@example.com"
    payload = {"email": email, "password": "password123", "agency_name": "Dup Agency"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.post("/auth/signup", json=payload)
        assert r1.status_code == 201

        r2 = await client.post("/auth/signup", json=payload)
        assert r2.status_code == 409
        assert r2.json()["detail"] == "Email already registered"


@_db_skip
async def test_refresh_rotates() -> None:
    from app.main import app

    email = f"ref+{uuid4().hex[:8]}@example.com"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        signup = await client.post(
            "/auth/signup",
            json={"email": email, "password": "password123", "agency_name": "Refresh Co"},
        )
        assert signup.status_code == 201
        refresh_token = signup.json()["refresh_token"]

        resp = await client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200, resp.text
        new_data = resp.json()
        assert "access_token" in new_data
        assert new_data["access_token"] != signup.json()["access_token"]
