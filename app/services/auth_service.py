from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.db.models import Subscription, Tenant, TenantAccount
from app.db.session import async_session_factory

_DUMMY_HASH = "$2b$12$" + "x" * 53


class EmailAlreadyRegistered(Exception):  # noqa: N818
    pass


class InvalidCredentials(Exception):  # noqa: N818
    pass


class AccountSuspended(Exception):  # noqa: N818
    pass


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "agency")[:50]


async def _unique_slug(session: AsyncSession, base: str) -> str:
    candidate = base
    for i in range(2, 52):
        exists = await session.scalar(select(Tenant.id).where(Tenant.slug == candidate))
        if exists is None:
            return candidate
        candidate = f"{base}-{i}"[:60]
    return f"{base[:40]}-{uuid4().hex[:6]}"


async def signup(email: str, password: str, agency_name: str) -> TenantAccount:
    email = email.strip().lower()
    settings = get_settings()
    async with async_session_factory() as session:
        dup = await session.scalar(
            select(TenantAccount.id).where(TenantAccount.email == email)
        )
        if dup is not None:
            raise EmailAlreadyRegistered()

        now = datetime.now(timezone.utc)  # noqa: UP017
        slug = await _unique_slug(session, _slugify(agency_name))

        tenant = Tenant(id=uuid4(), slug=slug, display_name=agency_name, status="trial")
        session.add(tenant)
        await session.flush()

        sub = Subscription(
            id=uuid4(),
            tenant_id=tenant.id,
            provider="mercadopago",
            status="trial",
            trial_ends_at=now + timedelta(days=settings.TRIAL_DAYS),
            currency="ARS",
        )
        session.add(sub)

        account = TenantAccount(
            id=uuid4(),
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            role="owner",
        )
        session.add(account)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise EmailAlreadyRegistered() from exc
        await session.refresh(account)
        return account


async def authenticate(email: str, password: str) -> TenantAccount:
    email = email.strip().lower()
    async with async_session_factory() as session:
        account = await session.scalar(
            select(TenantAccount).where(TenantAccount.email == email)
        )
        if account is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentials()
        if not verify_password(password, account.password_hash):
            raise InvalidCredentials()
        tenant = await session.get(Tenant, account.tenant_id)
        if tenant is not None and tenant.status == "suspended":
            raise AccountSuspended()
        return account


async def get_account_with_subscription(
    account_id: object,
) -> tuple[TenantAccount | None, Tenant | None, Subscription | None]:
    async with async_session_factory() as session:
        account = await session.get(TenantAccount, account_id)
        if account is None:
            return None, None, None
        tenant = await session.get(Tenant, account.tenant_id)
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == account.tenant_id)
        )
        return account, tenant, sub
