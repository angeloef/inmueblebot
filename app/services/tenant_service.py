"""Tenant resolution & lookups (V3 Phase 1).

The inbound webhook resolves which inmobiliaria a message belongs to by the Meta
``phone_number_id`` (decision D2). This module owns that lookup, with a small in-process
cache (the mapping changes only when an admin provisions/edits a tenant), plus helpers to
read a tenant's (decrypted) WhatsApp access token.

All lookups here run WITHOUT a tenant context set yet (we're deciding the tenant), so they
must read the ``tenants`` table directly — which is itself not tenant-scoped.
"""

from __future__ import annotations

import time
from uuid import UUID

from loguru import logger
from sqlalchemy import select

from app.core.crypto import decrypt_secret, encryption_available
from app.core.tenancy import default_tenant_id
from app.db.models.tenant import Tenant

# phone_number_id -> (tenant_id, ts). Short TTL: provisioning is rare, but we don't want a
# new number to be unroutable for long.
_RESOLVE_TTL = 300.0
_resolve_cache: dict[str, tuple[UUID | None, float]] = {}


def bust_tenant_cache() -> None:
    """Invalidate the phone_number_id→tenant cache (call after tenant CRUD)."""
    _resolve_cache.clear()


async def resolve_tenant_id_by_phone_number_id(phone_number_id: str | None) -> UUID | None:
    """Return the tenant id for a Meta ``phone_number_id``, or ``None`` if unknown.

    A return of ``None`` means the number is not provisioned — the caller should park the
    message rather than guess a tenant.
    """
    if not phone_number_id:
        return None

    now = time.monotonic()
    cached = _resolve_cache.get(phone_number_id)
    if cached and (now - cached[1]) < _RESOLVE_TTL:
        return cached[0]

    tenant_id: UUID | None = None
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            row = await session.execute(
                select(Tenant.id).where(Tenant.phone_number_id == phone_number_id)
            )
            tenant_id = row.scalar_one_or_none()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] tenant resolution failed for {phone_number_id}: {exc}")
        return None  # fail closed — don't misroute on a transient error

    _resolve_cache[phone_number_id] = (tenant_id, now)
    return tenant_id


async def get_tenant(tenant_id: UUID) -> Tenant | None:
    """Load a tenant row by id (no tenant scoping on the tenants table itself)."""
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            row = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            return row.scalar_one_or_none()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] get_tenant failed for {tenant_id}: {exc}")
        return None


async def get_tenant_access_token(tenant_id: UUID) -> str | None:
    """Return a tenant's DECRYPTED WhatsApp access token, or ``None``.

    Falls back to the env-configured token only for the default tenant (so the existing
    single-tenant deployment keeps sending without a DB token configured).
    """
    tenant = await get_tenant(tenant_id)
    if tenant and tenant.wa_access_token and encryption_available():
        try:
            return decrypt_secret(tenant.wa_access_token)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"[Tenancy] could not decrypt access token for {tenant_id}: {exc}")
            return None

    if tenant_id == default_tenant_id():
        from app.core.config import get_settings
        return get_settings().WHATSAPP_ACCESS_TOKEN
    return None
