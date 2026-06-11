"""Google OAuth 2.0 — Authorization Code flow (login/registro con Google).

Implementado con las libs ya presentes (httpx + google-auth), sin Authlib ni
SessionMiddleware. El flujo:

  1. /auth/google/login  → build_authorization_url() arma la URL de consentimiento
     con state (anti-CSRF) + nonce (anti-replay) y redirige.
  2. /auth/google/callback → exchange_code() canjea el code por tokens contra
     Google, y verify_id_token() valida firma/iss/aud/exp/nonce contra las JWKS de
     Google, devolviendo los claims (sub, email, email_verified, name).

Si faltan las credenciales (is_configured() == False) los endpoints devuelven 501.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Endpoints fijos del proveedor (OpenID Connect de Google).
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 — URL pública, no es secreto
_SCOPES = "openid email profile"


class GoogleOAuthError(Exception):
    """Falla recuperable del flujo OAuth (intercambio o verificación)."""


def is_configured() -> bool:
    s = get_settings()
    return bool(s.GOOGLE_OAUTH_CLIENT_ID and s.GOOGLE_OAUTH_CLIENT_SECRET)


def redirect_uri() -> str:
    """Redirect URI absoluta del callback. Explícita en config, o derivada de PUBLIC_API_URL."""
    s = get_settings()
    if s.GOOGLE_OAUTH_REDIRECT_URI:
        return s.GOOGLE_OAUTH_REDIRECT_URI
    base = s.PUBLIC_API_URL.rstrip("/")
    return f"{base}/api/auth/google/callback"


def build_authorization_url(state_token: str) -> str:
    """URL de consentimiento de Google. ``state_token`` es el JWT firmado (state+nonce).

    El nonce se manda por separado a Google para que lo incruste en el id_token; lo
    extraemos del propio state_token en el callback para compararlo.
    """
    s = get_settings()
    from app.core.security import decode_token  # local: evita ciclo de import

    nonce = decode_token(state_token).get("nonce", "")
    params = {
        "client_id": s.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": _SCOPES,
        "state": state_token,
        "nonce": nonce,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """Canjea el authorization code por tokens. Devuelve el id_token (JWT crudo).

    No usamos el access_token (no llamamos userinfo): el id_token verificado ya trae
    email/email_verified/name, y verificar su firma es más seguro que confiar en
    userinfo sin validar.
    """
    s = get_settings()
    data = {
        "code": code,
        "client_id": s.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": s.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_TOKEN_ENDPOINT, data=data)
    except httpx.HTTPError as exc:
        logger.warning("Google token exchange network error: %s", exc)
        raise GoogleOAuthError("token_exchange_failed") from exc

    if resp.status_code != 200:
        logger.warning("Google token exchange failed: %s %s", resp.status_code, resp.text[:200])
        raise GoogleOAuthError("token_exchange_failed")

    payload = resp.json()
    tok = payload.get("id_token")
    if not tok:
        raise GoogleOAuthError("missing_id_token")
    return tok


def verify_id_token(raw_id_token: str, expected_nonce: str) -> dict:
    """Verifica firma + iss + aud + exp contra las JWKS de Google y matchea el nonce.

    Devuelve claims: {sub, email, email_verified, name, ...}. Lanza GoogleOAuthError
    ante cualquier discrepancia (fail-closed).
    """
    s = get_settings()
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience=s.GOOGLE_OAUTH_CLIENT_ID,
        )
    except ValueError as exc:
        logger.warning("Google id_token verification failed: %s", exc)
        raise GoogleOAuthError("invalid_id_token") from exc

    # iss correcto (verify_oauth2_token ya lo chequea, pero somos explícitos).
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleOAuthError("invalid_issuer")

    # Anti-replay: el nonce del id_token debe ser el que mandamos en el authorize.
    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise GoogleOAuthError("nonce_mismatch")

    if not claims.get("sub") or not claims.get("email"):
        raise GoogleOAuthError("incomplete_claims")

    return claims
