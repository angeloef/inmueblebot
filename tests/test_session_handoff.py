"""Handoff de sesión landing→dashboard + single-use de tokens.

(Distinto del handoff del BOT en test_handoff.py — esto es el puente de SESIÓN
entre la landing y el dashboard.)

Unit/ASGI offline (sin DB/Redis) corren siempre. El happy-path end-to-end del
handoff requiere Postgres y se saltea sin DATABASE_URL (igual que test_auth.py).
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.core import config

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
    yield
    from app.db.session import async_session_factory

    bind = async_session_factory.kw.get("bind")
    if bind is not None:
        await bind.dispose()


# ---------------------------------------------------------------------------
# Unit: handoff token
# ---------------------------------------------------------------------------

def test_handoff_token_roundtrip() -> None:
    from app.core.security import create_handoff_token, decode_token

    acc, tid = uuid4(), uuid4()
    tok = create_handoff_token(acc, tid, "owner", "/dashboard/clientes")
    payload = decode_token(tok)
    assert payload["type"] == "handoff"
    assert payload["sub"] == str(acc)
    assert payload["tid"] == str(tid)
    assert payload["next"] == "/dashboard/clientes"
    assert payload["jti"]


def test_handoff_token_default_next() -> None:
    from app.core.security import create_handoff_token, decode_token

    payload = decode_token(create_handoff_token(uuid4(), uuid4(), "owner"))
    assert payload["next"] == "/"


# ---------------------------------------------------------------------------
# Unit: single-use marker fails CLOSED when Redis is unreachable
# ---------------------------------------------------------------------------

async def test_mark_jti_used_fails_closed_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import auth_service

    # Apuntar Redis a un puerto muerto → la conexión falla → debe devolver False
    # (jamás aceptar un token de un solo uso si no podemos garantizar unicidad).
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390/0")
    config.get_settings.cache_clear()
    ok = await auth_service.mark_jti_used("handoff", uuid4().hex, 90)
    assert ok is False


# ---------------------------------------------------------------------------
# ASGI offline: rechazos del callback de handoff (no tocan DB ni Redis)
# ---------------------------------------------------------------------------

def _client() -> httpx.AsyncClient:
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_handoff_missing_code_redirects_to_login() -> None:
    async with _client() as client:
        r = await client.get("/auth/handoff", follow_redirects=False)
        assert r.status_code == 303
        assert "error=handoff" in r.headers["location"]
        assert "/login" in r.headers["location"]


async def test_handoff_garbage_code_redirects_to_login() -> None:
    async with _client() as client:
        r = await client.get(
            "/auth/handoff", params={"code": "not-a-jwt"}, follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error=handoff" in r.headers["location"]


async def test_handoff_wrong_token_type_rejected() -> None:
    """Un access token (type=access) no sirve como código de handoff."""
    from app.core.security import create_access_token

    access = create_access_token(uuid4(), uuid4(), "owner")
    async with _client() as client:
        r = await client.get(
            "/auth/handoff", params={"code": access}, follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error=handoff" in r.headers["location"]


async def test_handoff_code_requires_auth() -> None:
    async with _client() as client:
        r = await client.post("/auth/handoff-code", json={})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# DB integration: full handoff (signup → handoff-code → handoff → cookies)
# ---------------------------------------------------------------------------

@_db_skip
async def test_handoff_full_flow_sets_dashboard_cookies() -> None:
    from app.main import app
    from app.services import auth_service

    email = f"handoff+{uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        signup = await client.post("/auth/signup", json={
            "email": email, "password": "password123", "agency_name": "Handoff Co",
        })
        assert signup.status_code == 201
        access = signup.json()["access_token"]

        # 1) pedir el código (con el bearer recién emitido) + deep-link
        code_resp = await client.post(
            "/auth/handoff-code",
            json={"next": "/dashboard/clientes"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert code_resp.status_code == 200, code_resp.text
        code = code_resp.json()["code"]

        # 2) canjearlo (mock del single-use Redis → primera vez)
        with patch.object(auth_service, "mark_jti_used", new=AsyncMock(return_value=True)):
            redeem = await client.get(
                "/auth/handoff", params={"code": code}, follow_redirects=False,
            )
        assert redeem.status_code == 303
        assert redeem.headers["location"] == "/dashboard/clientes"
        assert "vivienda_access" in redeem.headers.get("set-cookie", "")


@_db_skip
async def test_handoff_replay_rejected() -> None:
    """Un código ya canjeado (mark_jti_used → False) no abre sesión."""
    from app.main import app
    from app.services import auth_service

    email = f"hreplay+{uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        signup = await client.post("/auth/signup", json={
            "email": email, "password": "password123", "agency_name": "Replay Co",
        })
        access = signup.json()["access_token"]
        code = (await client.post(
            "/auth/handoff-code", json={},
            headers={"Authorization": f"Bearer {access}"},
        )).json()["code"]

        with patch.object(auth_service, "mark_jti_used", new=AsyncMock(return_value=False)):
            redeem = await client.get(
                "/auth/handoff", params={"code": code}, follow_redirects=False,
            )
        assert redeem.status_code == 303
        assert "error=handoff" in redeem.headers["location"]
        assert "vivienda_access" not in redeem.headers.get("set-cookie", "")
