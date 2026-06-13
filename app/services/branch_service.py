"""Sucursales (Enterprise multi-sucursal) — create/edit branch tenants + manager logins.

A "sucursal" is a CHILD tenant (``parent_tenant_id`` set) of an Enterprise org. It carries
its own Meta number + isolated data; billing stays on the org parent. See
``enterprise-multisucursal-design`` and ``app/db/models/tenant.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.crypto import encrypt_secret, encryption_available
from app.core.security import hash_password
from app.db.models import Tenant, TenantAccount
from app.db.session import async_session_factory
from app.services.auth_service import EmailAlreadyRegistered, _slugify, _unique_slug
from app.services.tenant_service import bust_tenant_cache


class BranchError(Exception):  # noqa: N818
    pass


class PhoneNumberInUse(BranchError):  # noqa: N818
    pass


async def create_branch(
    org_id: UUID,
    *,
    display_name: str,
    slug: str | None = None,
    timezone_: str = "America/Argentina/Cordoba",
    business_hours: str | None = None,
    phone_number_id: str | None = None,
    waba_id: str | None = None,
    wa_access_token: str | None = None,
    address: str | None = None,
) -> Tenant:
    """Create a sucursal (child tenant) under ``org_id``.

    The org must be a root tenant (not itself a branch). ``phone_number_id`` is the Meta
    routing key — unique across all tenants. ``wa_access_token`` is encrypted at rest.
    """
    async with async_session_factory() as session:
        org = await session.get(Tenant, org_id)
        if org is None:
            raise BranchError("Org not found")
        if org.parent_tenant_id is not None:
            raise BranchError("Cannot create a branch under another branch")

        unique_slug = await _unique_slug(session, _slugify(slug or display_name))

        if phone_number_id:
            dup = await session.scalar(
                select(Tenant.id).where(Tenant.phone_number_id == phone_number_id)
            )
            if dup is not None:
                raise PhoneNumberInUse()

        enc_token = (
            encrypt_secret(wa_access_token)
            if (wa_access_token and encryption_available())
            else None
        )

        branch = Tenant(
            id=uuid4(),
            parent_tenant_id=org_id,
            slug=unique_slug,
            display_name=display_name,
            company_name=org.company_name or org.display_name,
            timezone=timezone_,
            business_hours=business_hours,
            phone_number_id=phone_number_id or None,
            waba_id=waba_id or None,
            wa_access_token=enc_token,
            status="active",
            branding={"address": address} if address else None,
        )
        session.add(branch)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise PhoneNumberInUse() from exc
        await session.refresh(branch)

    bust_tenant_cache()  # a new number must be routable promptly
    logger.info(f"[Branch] created sucursal {branch.slug} under org {org_id}")
    return branch


async def update_branch(
    org_id: UUID,
    branch_id: UUID,
    *,
    display_name: str | None = None,
    business_hours: str | None = None,
    timezone_: str | None = None,
    phone_number_id: str | None = None,
    waba_id: str | None = None,
    wa_access_token: str | None = None,
    address: str | None = None,
) -> Tenant:
    """Edit a sucursal. Only fields passed (non-None) are changed. Validates ownership."""
    async with async_session_factory() as session:
        branch = await session.get(Tenant, branch_id)
        if branch is None or branch.parent_tenant_id != org_id:
            raise BranchError("Branch not found in your org")

        if phone_number_id is not None and phone_number_id != (branch.phone_number_id or ""):
            if phone_number_id:
                dup = await session.scalar(
                    select(Tenant.id).where(
                        Tenant.phone_number_id == phone_number_id, Tenant.id != branch_id
                    )
                )
                if dup is not None:
                    raise PhoneNumberInUse()
            branch.phone_number_id = phone_number_id or None

        if display_name is not None:
            branch.display_name = display_name
        if business_hours is not None:
            branch.business_hours = business_hours
        if timezone_ is not None:
            branch.timezone = timezone_
        if waba_id is not None:
            branch.waba_id = waba_id or None
        if wa_access_token:
            branch.wa_access_token = (
                encrypt_secret(wa_access_token) if encryption_available() else None
            )
        if address is not None:
            branding = dict(branch.branding or {})
            branding["address"] = address
            branch.branding = branding

        await session.commit()
        await session.refresh(branch)

    bust_tenant_cache()
    return branch


async def create_branch_manager(
    org_id: UUID,
    branch_id: UUID,
    email: str,
    password: str,
    full_name: str | None = None,
) -> TenantAccount:
    """Create a login (TenantAccount) pinned to a sucursal — the gerente de sucursal.

    The account's ``tenant_id`` is the branch, so existing RLS isolates them to it. Marked
    email-verified (the org dueño provisions it; no email round-trip).
    """
    email = email.strip().lower()
    async with async_session_factory() as session:
        branch = await session.get(Tenant, branch_id)
        if branch is None or branch.parent_tenant_id != org_id:
            raise BranchError("Branch not found in your org")

        dup = await session.scalar(
            select(TenantAccount.id).where(TenantAccount.email == email)
        )
        if dup is not None:
            raise EmailAlreadyRegistered()

        account = TenantAccount(
            id=uuid4(),
            tenant_id=branch_id,
            email=email,
            password_hash=hash_password(password),
            full_name=(full_name or "").strip() or None,
            role="owner",  # owner OF their branch
            email_verified_at=datetime.now(timezone.utc),  # noqa: UP017
        )
        session.add(account)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise EmailAlreadyRegistered() from exc
        await session.refresh(account)
        return account
