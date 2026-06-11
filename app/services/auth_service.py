from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


async def mark_jti_used(kind: str, jti: str, ttl_seconds: int) -> bool:
    """Single-use de tokens (handoff / registro Google): marca el jti en Redis.

    Devuelve True solo si el jti NO estaba usado (SET NX). FAIL-CLOSED: cualquier
    error de Redis devuelve False — un token de un solo uso jamás se acepta sin
    poder garantizar que es la primera vez.
    """
    import redis.asyncio as aioredis  # local: el módulo no necesita redis en import-time

    settings = get_settings()
    try:
        r = aioredis.Redis.from_url(
            settings.resolve_redis_url(),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            ok = await r.set(f"jti:{kind}:{jti}", "1", nx=True, ex=ttl_seconds)
            return bool(ok)
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("mark_jti_used(%s) Redis error — fail closed: %s", kind, exc)
        return False


class EmailAlreadyRegistered(Exception):  # noqa: N818
    pass


class InvalidCredentials(Exception):  # noqa: N818
    pass


class AccountSuspended(Exception):  # noqa: N818
    pass


class EmailNotVerified(Exception):  # noqa: N818
    """El proveedor OAuth no garantiza el email como verificado → no auto-linkear."""
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
        # password_hash es None en cuentas Google-only (todavía sin contraseña). En
        # ambos casos corremos el verify contra el dummy hash para no filtrar por
        # timing si la cuenta existe o no (user enumeration).
        if account is None or account.password_hash is None:
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


async def login_google(claims: dict) -> TenantAccount | None:
    """Loguea (o linkea) una cuenta EXISTENTE a partir de claims verificados de Google.

    claims = {sub, email, email_verified, name}. El email verificado es la clave de
    identidad que une métodos:

      1. email no verificado → EmailNotVerified (nunca auto-linkear)
      2. match por google_sub → login
      3. match por email → LINK (set google_sub) + login
      4. sin match → devuelve None (el caller redirige al registro explícito —
         acá NUNCA se crea un tenant; eso lo hace complete_google_signup()).
    """
    sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    email_verified = claims.get("email_verified")

    if not sub or not email:
        raise InvalidCredentials()
    # Google manda email_verified como bool true; algunos proveedores como string.
    if email_verified not in (True, "true"):
        raise EmailNotVerified()

    async with async_session_factory() as session:
        # 2) ¿Ya existe esta identidad Google?
        account = await session.scalar(
            select(TenantAccount).where(TenantAccount.google_sub == sub)
        )

        # 3) ¿Existe una cuenta con ese email (creada con contraseña)? → linkear.
        if account is None:
            account = await session.scalar(
                select(TenantAccount).where(TenantAccount.email == email)
            )
            if account is not None:
                account.google_sub = sub
                # Google ya verificó el email: marcarlo verificado si no lo estaba.
                if account.email_verified_at is None:
                    account.email_verified_at = datetime.now(timezone.utc)  # noqa: UP017

        # 4) Sin match → registro explícito (no se crea nada acá).
        if account is None:
            return None

        # Suspensión: mismo check que authenticate().
        tenant = await session.get(Tenant, account.tenant_id)
        if tenant is not None and tenant.status == "suspended":
            await session.rollback()
            raise AccountSuspended()

        await session.commit()
        await session.refresh(account)
        return account


async def complete_google_signup(
    google_sub: str, email: str, name: str, agency_name: str
) -> TenantAccount:
    """Crea la cuenta Google-only una vez que el usuario eligió el nombre de su
    inmobiliaria (paso 2 del registro con Google).

    La identidad (google_sub/email) viene de un registration token firmado y de un
    solo uso — el id_token de Google ya fue verificado en el callback. Crea Tenant +
    Subscription(trial) + TenantAccount(password_hash=NULL), idéntico al signup con
    contraseña salvo el método.
    """
    email = email.strip().lower()
    if not google_sub or not email:
        raise InvalidCredentials()

    settings = get_settings()
    async with async_session_factory() as session:
        # Carrera TOCTOU: el email o la identidad Google se registraron entre el
        # callback y este submit → 409 (el front sugiere iniciar sesión).
        dup = await session.scalar(
            select(TenantAccount.id).where(
                (TenantAccount.email == email)
                | (TenantAccount.google_sub == google_sub)
            )
        )
        if dup is not None:
            raise EmailAlreadyRegistered()

        now = datetime.now(timezone.utc)  # noqa: UP017
        slug = await _unique_slug(session, _slugify(agency_name))

        tenant = Tenant(id=uuid4(), slug=slug, display_name=agency_name, status="trial")
        session.add(tenant)
        await session.flush()

        session.add(Subscription(
            id=uuid4(),
            tenant_id=tenant.id,
            provider="mercadopago",
            status="trial",
            trial_ends_at=now + timedelta(days=settings.TRIAL_DAYS),
            currency="ARS",
        ))

        account = TenantAccount(
            id=uuid4(),
            tenant_id=tenant.id,
            email=email,
            password_hash=None,          # Google-only hasta que setee contraseña
            google_sub=google_sub,
            full_name=(name or "").strip() or None,
            role="owner",
            email_verified_at=now,       # Google ya lo verificó
        )
        session.add(account)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise EmailAlreadyRegistered() from exc
        await session.refresh(account)
        return account
