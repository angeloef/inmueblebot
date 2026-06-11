from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


def _encode(claims: dict[str, Any], ttl: timedelta, token_type: str) -> str:
    settings = get_settings()
    now = _now()
    payload = {
        **claims,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _base_claims(account_id: UUID, tenant_id: UUID, role: str) -> dict[str, Any]:
    # jti = unique token id. Guarantees every access/refresh token is distinct even
    # when minted within the same second (iat/exp are second-resolution), so a
    # refresh always rotates to a new token. Also a hook for future revocation lists.
    return {"sub": str(account_id), "tid": str(tenant_id), "role": role, "jti": uuid4().hex}


def create_access_token(account_id: UUID, tenant_id: UUID, role: str) -> str:
    settings = get_settings()
    return _encode(
        _base_claims(account_id, tenant_id, role),
        timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN),
        "access",
    )


def create_refresh_token(account_id: UUID, tenant_id: UUID, role: str) -> str:
    settings = get_settings()
    return _encode(
        _base_claims(account_id, tenant_id, role),
        timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
        "refresh",
    )


def create_email_token(account_id: UUID, token_type: str, token_version: int | None = None) -> str:
    claims: dict[str, Any] = {"sub": str(account_id)}
    if token_version is not None:
        claims["tv"] = token_version
    return _encode(claims, timedelta(hours=24), token_type)


# TTL del state OAuth: el usuario tiene 10 min para completar el flujo en Google.
_OAUTH_STATE_TTL = timedelta(minutes=10)

# Handoff de sesión landing→dashboard: ventana mínima (un redirect inmediato).
_HANDOFF_TTL = timedelta(seconds=60)

# Registro Google pendiente: tiempo para tipear el nombre de la inmobiliaria.
_GOOGLE_SIGNUP_TTL = timedelta(minutes=15)


def create_handoff_token(
    account_id: UUID, tenant_id: UUID, role: str, next_path: str = "/"
) -> str:
    """Token de un solo uso que cruza la sesión de la landing al dashboard.

    60s de vida, single-use (jti marcado en Redis al canje). Nunca transporta el
    refresh token: el canje re-emite cookies frescas en el origen de la API.
    ``next_path`` es un path relativo ya validado (deep-link del dashboard).
    """
    claims = {**_base_claims(account_id, tenant_id, role), "next": next_path}
    return _encode(claims, _HANDOFF_TTL, "handoff")


def create_google_signup_token(google_sub: str, email: str, name: str) -> str:
    """Registro Google pendiente: identidad ya verificada, falta el nombre de la
    inmobiliaria. Solo permite CREAR una cuenta (no abre sesión de existentes).
    Single-use vía jti + Redis en /auth/google/complete."""
    claims = {"gsub": google_sub, "email": email, "name": name, "jti": uuid4().hex}
    return _encode(claims, _GOOGLE_SIGNUP_TTL, "g_signup")


def create_oauth_state_token(state: str, nonce: str) -> str:
    """Firma un state OAuth (anti-CSRF) que embebe el nonce (anti-replay del id_token).

    Se envía como parámetro ``state`` a Google y, en paralelo, se setea como cookie
    httpOnly. En el callback se exige que ambos coincidan (double-submit) y que la
    firma + exp sean válidos, antes de comparar el nonce contra el id_token.
    """
    return _encode({"st": state, "nonce": nonce}, _OAUTH_STATE_TTL, "oauth_state")


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica y valida firma+exp. Lanza jwt.ExpiredSignatureError / jwt.InvalidTokenError."""
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
