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
from app.db.models.tenant import Tenant, TenantSettings

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


async def list_active_tenant_ids() -> list[UUID]:
    """Return ids of every tenant a scheduled job should process.

    A tenant counts as active unless explicitly ``status='disabled'`` (NULL status =
    legacy/active). The ``tenants`` table is not tenant-scoped, so this reads it directly.
    """
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            rows = await session.execute(
                select(Tenant.id).where(
                    (Tenant.status.is_(None)) | (Tenant.status != "disabled")
                )
            )
            return [r[0] for r in rows.all()]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] list_active_tenant_ids failed: {exc}")
        return []


async def list_operational_tenant_ids() -> list[UUID]:
    """Active tenants that actually OPERATE (leaf tenants) — for per-tenant scheduled jobs.

    Excludes Enterprise org parents (tenants that have ≥1 child sucursal). An org parent has
    no Meta number nor data of its own, and under org-aware RLS its GUC would expose ALL its
    branches' rows — so iterating it in a per-tenant job would double-process every child
    (duplicate reminders). Branches (have a parent) and standalone tenants (no parent, no
    children) are included.
    """
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            # Ids that ARE a parent of some other tenant (= org parents to exclude).
            parents_subq = (
                select(Tenant.parent_tenant_id)
                .where(Tenant.parent_tenant_id.is_not(None))
                .distinct()
            )
            rows = await session.execute(
                select(Tenant.id).where(
                    ((Tenant.status.is_(None)) | (Tenant.status != "disabled"))
                    & (Tenant.id.not_in(parents_subq))
                )
            )
            return [r[0] for r in rows.all()]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] list_operational_tenant_ids failed: {exc}")
        return []


async def list_root_tenant_ids() -> list[UUID]:
    """Active ROOT tenants (parent_tenant_id IS NULL) = Enterprise orgs + standalones.

    Used by org-level jobs (e.g. the monthly executive report): a sucursal (child) rolls its
    data into its org, so only roots get a consolidated report.
    """
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            rows = await session.execute(
                select(Tenant.id).where(
                    Tenant.parent_tenant_id.is_(None)
                    & ((Tenant.status.is_(None)) | (Tenant.status != "disabled"))
                )
            )
            return [r[0] for r in rows.all()]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] list_root_tenant_ids failed: {exc}")
        return []


async def get_child_tenant_ids(parent_id: UUID) -> list[UUID]:
    """Return the ids of every sucursal (child tenant) under an Enterprise org."""
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            rows = await session.execute(
                select(Tenant.id).where(Tenant.parent_tenant_id == parent_id)
            )
            return [r[0] for r in rows.all()]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] get_child_tenant_ids failed for {parent_id}: {exc}")
        return []


async def list_branches(parent_id: UUID) -> list[Tenant]:
    """Return the full Tenant rows for every sucursal under an org (for selector/CRUD)."""
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            rows = await session.execute(
                select(Tenant).where(Tenant.parent_tenant_id == parent_id)
                .order_by(Tenant.display_name)
            )
            return list(rows.scalars().all())
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] list_branches failed for {parent_id}: {exc}")
        return []


async def get_tenant_setting(tenant_id: UUID, key: str, default: str | None = None) -> str | None:
    """Read a per-tenant key/value setting (``tenant_settings`` table)."""
    try:
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            row = await session.execute(
                select(TenantSettings.value).where(
                    TenantSettings.tenant_id == tenant_id,
                    TenantSettings.key == key,
                )
            )
            value = row.scalar_one_or_none()
            return value if value is not None else default
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Tenancy] get_tenant_setting({key}) failed for {tenant_id}: {exc}")
        return default


async def set_tenant_setting(tenant_id: UUID, key: str, value: str | None) -> None:
    """Upsert a per-tenant key/value setting (``tenant_settings`` table)."""
    from app.db.session import async_session_factory
    async with async_session_factory() as session:
        existing = await session.execute(
            select(TenantSettings).where(
                TenantSettings.tenant_id == tenant_id,
                TenantSettings.key == key,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            session.add(TenantSettings(tenant_id=tenant_id, key=key, value=value))
        else:
            row.value = value
        await session.commit()


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
