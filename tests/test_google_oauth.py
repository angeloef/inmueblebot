"""Google OAuth tests (login/registro con Google).

Unit tests (offline, mockean Google) corren siempre. Los tests de integración del
callback requieren Postgres y se saltan salvo que DATABASE_URL / TEST_DATABASE_URL
esté seteado (mismo patrón que test_auth.py).

Run unit-only:
    pytest tests/test_google_oauth.py -k "unit or Unit or not db"
"""
from __future__ import annotations

import os
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from app.core import config

TEST_SECRET = "test-secret-key-32-chars-minimum-xx"
TEST_CLIENT_ID = "test-client-id.apps.googleusercontent.com"

_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_db_skip = pytest.mark.skipif(
    not _DB_URL,
    reason="DATABASE_URL / TEST_DATABASE_URL not set (Postgres required)",
)


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", TEST_CLIENT_ID)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.example.test")
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
# Unit: state token
# ---------------------------------------------------------------------------

def test_oauth_state_token_roundtrip() -> None:
    from app.core.security import create_oauth_state_token, decode_token

    tok = create_oauth_state_token("the-state", "the-nonce")
    payload = decode_token(tok)
    assert payload["type"] == "oauth_state"
    assert payload["st"] == "the-state"
    assert payload["nonce"] == "the-nonce"


# ---------------------------------------------------------------------------
# Unit: google_oauth module config + URL building
# ---------------------------------------------------------------------------

def test_is_configured_true_when_creds_present() -> None:
    from app.services import google_oauth

    assert google_oauth.is_configured() is True


def test_is_configured_false_when_creds_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import google_oauth

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    config.get_settings.cache_clear()
    assert google_oauth.is_configured() is False


def test_redirect_uri_derived_from_public_api_url() -> None:
    from app.services import google_oauth

    assert google_oauth.redirect_uri() == "https://api.example.test/api/auth/google/callback"


def test_redirect_uri_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import google_oauth

    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://custom.test/cb")
    config.get_settings.cache_clear()
    assert google_oauth.redirect_uri() == "https://custom.test/cb"


def test_build_authorization_url_has_required_params() -> None:
    from app.core.security import create_oauth_state_token
    from app.services import google_oauth

    state_token = create_oauth_state_token("s", "my-nonce")
    url = google_oauth.build_authorization_url(state_token)
    qs = parse_qs(urlparse(url).query)

    assert qs["client_id"][0] == TEST_CLIENT_ID
    assert qs["response_type"][0] == "code"
    assert qs["scope"][0] == "openid email profile"
    assert qs["state"][0] == state_token
    assert qs["nonce"][0] == "my-nonce"
    assert urlparse(url).netloc == "accounts.google.com"


# ---------------------------------------------------------------------------
# Unit: id_token verification (mocking google-auth)
# ---------------------------------------------------------------------------

def test_verify_id_token_ok() -> None:
    from app.services import google_oauth

    fake_claims = {
        "iss": "https://accounts.google.com",
        "sub": "123",
        "email": "x@example.com",
        "email_verified": True,
        "nonce": "n1",
    }
    with patch.object(google_oauth.google_id_token, "verify_oauth2_token", return_value=fake_claims):
        out = google_oauth.verify_id_token("rawtok", "n1")
    assert out["sub"] == "123"


def test_verify_id_token_nonce_mismatch() -> None:
    from app.services import google_oauth

    fake_claims = {"iss": "https://accounts.google.com", "sub": "1", "email": "x@e.com", "nonce": "OTHER"}
    with patch.object(google_oauth.google_id_token, "verify_oauth2_token", return_value=fake_claims):
        with pytest.raises(google_oauth.GoogleOAuthError):
            google_oauth.verify_id_token("rawtok", "expected")


def test_verify_id_token_bad_issuer() -> None:
    from app.services import google_oauth

    fake_claims = {"iss": "evil.com", "sub": "1", "email": "x@e.com", "nonce": "n"}
    with patch.object(google_oauth.google_id_token, "verify_oauth2_token", return_value=fake_claims):
        with pytest.raises(google_oauth.GoogleOAuthError):
            google_oauth.verify_id_token("rawtok", "n")


def test_verify_id_token_invalid_signature() -> None:
    from app.services import google_oauth

    with patch.object(
        google_oauth.google_id_token, "verify_oauth2_token", side_effect=ValueError("bad sig")
    ):
        with pytest.raises(google_oauth.GoogleOAuthError):
            google_oauth.verify_id_token("rawtok", "n")


# ---------------------------------------------------------------------------
# DB integration: callback flow, linking, signup, recovery
# ---------------------------------------------------------------------------

def _mock_google(email: str, sub: str, *, verified: bool = True, name: str = "Test User"):
    """Devuelve los dos patches (exchange_code + verify_id_token) ya configurados."""
    from app.services import google_oauth

    claims = {
        "iss": "https://accounts.google.com",
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "name": name,
        "nonce": "ignored-in-mock",
    }

    async def _fake_exchange(code: str) -> str:
        return "raw-id-token"

    def _fake_verify(raw: str, nonce: str) -> dict:
        return claims

    return (
        patch.object(google_oauth, "exchange_code", _fake_exchange),
        patch.object(google_oauth, "verify_id_token", _fake_verify),
    )


async def _do_google_login(client: httpx.AsyncClient, email: str, sub: str, **kw):
    """Ejecuta el handshake completo: /login (state cookie) → /callback mockeado."""
    login = await client.get("/auth/google/login", follow_redirects=False)
    assert login.status_code == 302, login.text
    state_token = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    p1, p2 = _mock_google(email, sub, **kw)
    with p1, p2:
        cb = await client.get(
            "/auth/google/callback",
            params={"code": "authcode", "state": state_token},
            follow_redirects=False,
        )
    return cb


@_db_skip
async def test_google_signup_creates_account() -> None:
    from app.main import app

    email = f"gsignup+{uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        cb = await _do_google_login(client, email, sub=f"sub-{uuid4().hex}")
        assert cb.status_code == 303, cb.text
        # Sesión abierta: cookies de access/refresh seteadas en el redirect.
        set_cookie = cb.headers.get("set-cookie", "")
        assert "vivienda_access" in set_cookie

        # /auth/me con esas cookies funciona y reporta auth_methods=["google"].
        me = await client.get("/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["auth_methods"] == ["google"]


@_db_skip
async def test_google_links_to_existing_password_account() -> None:
    from app.main import app

    email = f"glink+{uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Cuenta creada con contraseña.
        signup = await client.post("/auth/signup", json={
            "email": email, "password": "password123", "agency_name": "Link Co",
        })
        assert signup.status_code == 201

        # Login con Google del mismo email → linkea (no crea otra cuenta).
        cb = await _do_google_login(client, email, sub=f"sub-{uuid4().hex}")
        assert cb.status_code == 303, cb.text

        me = await client.get("/auth/me")
        assert me.status_code == 200
        assert set(me.json()["auth_methods"]) == {"password", "google"}


@_db_skip
async def test_google_unverified_email_rejected() -> None:
    from app.main import app

    email = f"gunver+{uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        cb = await _do_google_login(client, email, sub=f"sub-{uuid4().hex}", verified=False)
        assert cb.status_code == 303
        assert "error=email_unverified" in cb.headers["location"]


@_db_skip
async def test_google_callback_rejects_state_mismatch() -> None:
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        login = await client.get("/auth/google/login", follow_redirects=False)
        assert login.status_code == 302
        # Mandamos un state que NO coincide con la cookie → rechazo.
        cb = await client.get(
            "/auth/google/callback",
            params={"code": "authcode", "state": "forged-state-token"},
            follow_redirects=False,
        )
        assert cb.status_code == 303
        assert "error=state" in cb.headers["location"]


@_db_skip
async def test_google_only_account_can_set_password_via_reset() -> None:
    """Recuperación cruzada: cuenta Google-only puede establecer contraseña y luego
    loguear con ambos métodos."""
    from sqlalchemy import select

    from app.core.security import create_email_token
    from app.db.models import TenantAccount
    from app.db.session import async_session_factory
    from app.main import app

    email = f"grecover+{uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        cb = await _do_google_login(client, email, sub=f"sub-{uuid4().hex}")
        assert cb.status_code == 303

        # login con contraseña debe fallar (password_hash NULL) sin romper.
        bad = await client.post("/auth/login", json={"email": email, "password": "whatever123"})
        assert bad.status_code == 401

        # Emitimos un token de reset (como haría forgot-password) y seteamos contraseña.
        async with async_session_factory() as session:
            acc = await session.scalar(select(TenantAccount).where(TenantAccount.email == email))
            assert acc is not None
            assert acc.password_hash is None
            token = create_email_token(acc.id, "reset", acc.token_version)

        reset = await client.post(
            "/auth/reset-password", json={"token": token, "new_password": "brandnew123"},
        )
        assert reset.status_code == 200, reset.text

        # Ahora login con contraseña funciona.
        good = await client.post("/auth/login", json={"email": email, "password": "brandnew123"})
        assert good.status_code == 200
