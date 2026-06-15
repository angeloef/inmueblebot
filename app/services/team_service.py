from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.models import Tenant, TenantAccount, TenantMember
from app.db.models.tenant_member import MEMBER_ACCEPTED, MEMBER_PENDING
from app.db.session import async_session_factory
from app.services import email_service

logger = logging.getLogger(__name__)


class EmailAlreadyHasAccount(Exception):
    """El email ya tiene una TenantAccount global (1 user = 1 tenant)."""


class AlreadyInvited(Exception):
    """El email ya fue invitado a este tenant."""


class InviteNotFound(Exception):
    """Token inexistente o status != pending."""


class InviteExpired(Exception):
    """Token válido pero vencido."""


class MemberNotFound(Exception):
    pass


class CannotRemoveOwner(Exception):
    pass


class CannotRemoveSelf(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def invite_member(
    tenant_id: object,
    invited_by_account_id: object,
    email: str,
    name: str | None,
) -> TenantMember:
    email = email.strip().lower()
    settings = get_settings()
    async with async_session_factory() as session:
        existing_account = await session.scalar(
            select(TenantAccount.id).where(TenantAccount.email == email)
        )
        if existing_account is not None:
            raise EmailAlreadyHasAccount()

        dup = await session.scalar(
            select(TenantMember.id).where(
                (TenantMember.tenant_id == tenant_id) & (TenantMember.email == email)
            )
        )
        if dup is not None:
            raise AlreadyInvited()

        tenant = await session.get(Tenant, tenant_id)
        agency_name = tenant.display_name if tenant else "tu inmobiliaria"

        token = secrets.token_urlsafe(32)
        member = TenantMember(
            tenant_id=tenant_id,
            email=email,
            name=(name or "").strip() or None,
            is_admin=True,
            status=MEMBER_PENDING,
            invite_token=token,
            invite_expires_at=_now() + timedelta(days=settings.INVITE_TOKEN_TTL_DAYS),
        )
        session.add(member)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise AlreadyInvited() from exc
        await session.refresh(member)

    invite_url = f"{settings.PUBLIC_APP_URL.rstrip('/')}/invite/{token}"
    await email_service.send_invite_email(email, agency_name, invite_url)
    return member


async def list_members(tenant_id: object) -> list[object]:
    """Miembros del equipo: cuentas reales del tenant (owner/admins) + invitaciones.

    La pestaña Equipos muestra filas de ``TenantMember``, pero el owner (y cualquier
    ``TenantAccount`` creada fuera del flujo de invitación) no tiene fila de miembro.
    Sintetizamos una entrada por cada cuenta sin ``TenantMember`` asociado para que
    aparezcan en el listado con su rol e información.
    """
    async with async_session_factory() as session:
        res = await session.execute(
            select(TenantMember)
            .where(TenantMember.tenant_id == tenant_id)
            .order_by(TenantMember.created_at.desc())
        )
        members = list(res.scalars().all())
        linked_account_ids = {m.account_id for m in members if m.account_id is not None}

        acc_res = await session.execute(
            select(TenantAccount)
            .where(TenantAccount.tenant_id == tenant_id)
            .order_by(TenantAccount.created_at.asc())
        )
        accounts = list(acc_res.scalars().all())

        synthetic = [
            SimpleNamespace(
                id=acc.id,
                email=acc.email,
                name=acc.full_name,
                avatar_color=None,
                photo_url=None,
                is_admin=acc.role in ("owner", "admin", "superadmin"),
                status=MEMBER_ACCEPTED,
                role=acc.role,
                created_at=acc.created_at,
            )
            for acc in accounts
            if acc.id not in linked_account_ids
        ]

        # Cuentas reales primero (owner arriba), luego invitaciones más recientes.
        return synthetic + members


async def remove_member(tenant_id: object, member_id: object, requesting_account_id: object | None = None) -> None:
    async with async_session_factory() as session:
        member = await session.get(TenantMember, member_id)
        if member is None or member.tenant_id != tenant_id:
            raise MemberNotFound()
        if member.account_id is not None:
            if requesting_account_id is not None and member.account_id == requesting_account_id:
                raise CannotRemoveSelf()
            account = await session.get(TenantAccount, member.account_id)
            if account is not None:
                if account.role == "owner":
                    raise CannotRemoveOwner()
                await session.delete(account)
        await session.delete(member)
        await session.commit()


async def get_invite_info(token: str) -> tuple[str, str] | None:
    """Returns (email, agency_name) if valid and pending; None otherwise (anti-enumeration)."""
    async with async_session_factory() as session:
        member = await session.scalar(
            select(TenantMember).where(
                (TenantMember.invite_token == token)
                & (TenantMember.status == MEMBER_PENDING)
            )
        )
        if member is None:
            return None
        if member.invite_expires_at is not None and member.invite_expires_at < _now():
            return None
        tenant = await session.get(Tenant, member.tenant_id)
        agency_name = tenant.display_name if tenant else "la inmobiliaria"
        return member.email, agency_name


async def accept_invite_password(token: str, name: str | None, password: str) -> TenantAccount:
    from app.core.security import hash_password  # local import to avoid any circular issues
    async with async_session_factory() as session:
        member = await session.scalar(
            select(TenantMember).where(
                (TenantMember.invite_token == token)
                & (TenantMember.status == MEMBER_PENDING)
            )
        )
        if member is None:
            raise InviteNotFound()
        if member.invite_expires_at is not None and member.invite_expires_at < _now():
            raise InviteExpired()

        dup = await session.scalar(
            select(TenantAccount.id).where(TenantAccount.email == member.email)
        )
        if dup is not None:
            raise EmailAlreadyHasAccount()

        account = TenantAccount(
            tenant_id=member.tenant_id,
            email=member.email,
            password_hash=hash_password(password),
            role="admin",
        )
        resolved_name = (name or member.name or "").strip() or None
        if resolved_name:
            account.full_name = resolved_name
        account.email_verified_at = _now()

        session.add(account)
        await session.flush()

        member.status = MEMBER_ACCEPTED
        member.invite_token = None
        member.invite_expires_at = None
        member.account_id = account.id
        if resolved_name and not member.name:
            member.name = resolved_name

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise EmailAlreadyHasAccount() from exc
        await session.refresh(account)
        return account
