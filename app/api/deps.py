from __future__ import annotations

import hmac
from collections.abc import AsyncGenerator
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_token
from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.db.models import Subscription, TenantAccount
from app.db.session import async_session_factory
from app.services.subscription_service import subscription_grants_access

# Cookie httpOnly que setea /auth/* y lee el dashboard Vite (mismo origen vía el
# proxy /api). El browser nunca ve el JWT en JS — mismo patrón que el front Next.js.
ACCESS_COOKIE_NAME = "vivienda_access"

# auto_error=False: el token puede venir por header Bearer (API / Next.js BFF) O
# por la cookie httpOnly (dashboard Vite). Resolvemos la fuente manualmente.
_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _account_id_from_token(token: str) -> UUID:
    """Decodifica un access token y devuelve el account_id. 401 si es inválido."""
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token") from exc
    if payload.get("type") != "access":
        raise _unauthorized("Invalid token type")
    try:
        account_id = UUID(payload["sub"])
        UUID(payload["tid"])
    except (KeyError, ValueError, TypeError) as exc:
        raise _unauthorized("Invalid token") from exc
    return account_id


async def _load_account(account_id: UUID) -> TenantAccount:
    async with async_session_factory() as session:
        res = await session.execute(
            select(TenantAccount).where(TenantAccount.id == account_id)
        )
        account = res.scalar_one_or_none()
    if account is None:
        raise _unauthorized("Invalid token")
    return account


async def get_current_account(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
    access_cookie: str | None = Cookie(default=None, alias=ACCESS_COOKIE_NAME),  # noqa: B008
) -> AsyncGenerator[TenantAccount, None]:
    token = creds.credentials if creds else access_cookie
    if not token:
        raise _unauthorized("Not authenticated")
    account = await _load_account(_account_id_from_token(token))

    ctx_token = set_current_tenant(account.tenant_id)
    try:
        yield account
    finally:
        reset_current_tenant(ctx_token)


async def require_superadmin(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),  # noqa: B008
    x_admin_api_key: str | None = Header(default=None, alias="x-admin-api-key"),  # noqa: B008
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
    access_cookie: str | None = Cookie(default=None, alias=ACCESS_COOKIE_NAME),  # noqa: B008
) -> AsyncGenerator[TenantAccount | None, None]:
    """Auth de super-admin: acepta la ADMIN_API_KEY global (ops) O un JWT con role
    ``superadmin`` (el dueño logueado en el dashboard).

    Rutas a nivel plataforma (gestión de tenants, reindex, cleanup, simulate). La
    key global no resuelve tenant (ve todo); el JWT superadmin setea su contexto.
    Fail-closed: cualquier otra cosa → 401/403.
    """
    settings = get_settings()
    api_key = x_api_key or x_admin_api_key
    if api_key and settings.ADMIN_API_KEY and hmac.compare_digest(api_key, settings.ADMIN_API_KEY):
        yield None
        return

    token = creds.credentials if creds else access_cookie
    if not token:
        raise _unauthorized("Not authenticated")
    account = await _load_account(_account_id_from_token(token))
    if account.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    ctx_token = set_current_tenant(account.tenant_id)
    try:
        yield account
    finally:
        reset_current_tenant(ctx_token)


def require_role(*roles: str):  # noqa: ANN201
    async def _checker(
        account: TenantAccount = Depends(get_current_account),  # noqa: B008
    ) -> TenantAccount:
        if account.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return account
    return _checker


async def require_active_subscription(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> TenantAccount:
    """Gating de suscripción: deja pasar solo trial vigente o suscripción activa.

    Devuelve 402 (Payment Required) si el trial venció o la suscripción está
    pausada/cancelada. ``subscriptions`` es global (sin RLS), así que se consulta
    con el tenant del account ya resuelto por ``get_current_account``.
    """
    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == account.tenant_id)
        )
    if not subscription_grants_access(sub):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required",
        )
    return account
