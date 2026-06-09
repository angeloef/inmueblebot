from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

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
    return {"sub": str(account_id), "tid": str(tenant_id), "role": role}


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


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica y valida firma+exp. Lanza jwt.ExpiredSignatureError / jwt.InvalidTokenError."""
    settings = get_settings()
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
