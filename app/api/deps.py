from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.security import decode_token
from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.db.models import Subscription, TenantAccount
from app.db.session import async_session_factory
from app.services.subscription_service import subscription_grants_access

_bearer = HTTPBearer(auto_error=True)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_account(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),  # noqa: B008
) -> AsyncGenerator[TenantAccount, None]:
    token = creds.credentials
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

    async with async_session_factory() as session:
        res = await session.execute(
            select(TenantAccount).where(TenantAccount.id == account_id)
        )
        account = res.scalar_one_or_none()
    if account is None:
        raise _unauthorized("Invalid token")

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
