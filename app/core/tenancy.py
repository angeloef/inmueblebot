"""Tenant context & scoping primitives (V3 Phase 1 — multi-tenancy foundation).

A "tenant" here is an **inmobiliaria** (the agency that uses InmuebleBot) — the SaaS
sense, NOT the property renter/inquilino. See `v3-router-build-plan.md` §D1.

Three things live here so every layer agrees:
1. A per-task ``ContextVar`` holding the current tenant id (set once per webhook change).
2. The registry that maps each tenant-scoped table to *its* tenant column name. Almost
   every table uses ``tenant_id``; ``contracts`` already uses ``tenant_id`` for the
   *renter* (inquilino, FK→users), so its agency FK is ``org_id`` to avoid the clash.
3. The transaction-scoped GUC helper (``set_config('app.current_tenant_id', …)``) that
   drives Postgres RLS and the engine-level safety hook.

Bulletproof default-tenant fallback (V2 safety): when no tenant context is set, every
scoped path resolves to ``DEFAULT_TENANT_ID`` so V2 (which has no tenant concept) keeps
serving the existing inmobiliaria exactly as before.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import UUID

from app.core.config import get_settings

# Postgres GUC name read by every RLS policy. The ``true`` (missing_ok) second arg to
# current_setting() in the policy makes it NULL-safe for non-app sessions.
TENANT_GUC = "app.current_tenant_id"


def default_tenant_id() -> UUID:
    """The default tenant (existing inmobiliaria). Fallback for any unscoped path."""
    return UUID(get_settings().DEFAULT_TENANT_ID)


# --- Per-table tenant column registry ---------------------------------------------
# Default column name for the agency FK.
DEFAULT_TENANT_COLUMN = "tenant_id"

# Tables whose agency FK is NOT named ``tenant_id`` (collision overrides).
# ``contracts.tenant_id`` already means the renter (inquilino), so the agency FK is ``org_id``.
_TENANT_COLUMN_OVERRIDES: dict[str, str] = {
    "contracts": "org_id",
}

# Reference/lookup tables shared across all agencies → intentionally NOT tenant-scoped.
# ``economic_indices`` holds the national IPC series (same for every inmobiliaria).
GLOBAL_TABLES: frozenset[str] = frozenset({"economic_indices"})

# Every tenant-scoped table the V3 plan covers (derived from Base.metadata, see Phase 1).
# Child cobranzas tables (charges, contract_expenses) are scoped directly too so RLS does
# not depend on a join back to contracts.
TENANT_SCOPED_TABLES: frozenset[str] = frozenset({
    "users",
    "properties",
    "conversations",
    "messages",
    "appointments",
    "faq_entries",
    "user_episodes",
    "zone_stats",
    "search_failures",
    "contracts",
    "charges",
    "contract_expenses",
    "tenant_site_briefs",
    "documents",
})


def tenant_column(table: str) -> str:
    """Return the agency-FK column name for ``table`` (``tenant_id`` unless overridden)."""
    return _TENANT_COLUMN_OVERRIDES.get(table, DEFAULT_TENANT_COLUMN)


# --- Per-task tenant context ------------------------------------------------------
_current_tenant: ContextVar[UUID | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: UUID | None) -> Token:
    """Set the current tenant for this async task. Returns a token to reset with.

    Pass ``None`` to clear (the resolver below then falls back to the default tenant).
    """
    return _current_tenant.set(tenant_id)


def reset_current_tenant(token: Token) -> None:
    """Restore the previous tenant context (use the token from ``set_current_tenant``)."""
    _current_tenant.reset(token)


def get_current_tenant() -> UUID | None:
    """Return the explicitly-set tenant for this task, or ``None`` if unset."""
    return _current_tenant.get()


def resolve_tenant_id() -> UUID:
    """Current tenant, falling back to the default tenant when no context is set.

    This is the bulletproof fallback that keeps V2 / cron / ad-hoc sessions working:
    an unscoped path always resolves to the existing inmobiliaria.
    """
    return _current_tenant.get() or default_tenant_id()


class tenant_scope:
    """Context manager that pins the current tenant for the enclosed block.

    Used by background jobs that iterate over tenants: each tenant gets its own
    scoped block so every DB session opened inside is filtered by that tenant's RLS
    (the GUC listener reads ``resolve_tenant_id()``). Restores the previous tenant on
    exit so nested/sequential scopes don't leak.

        with tenant_scope(tid):
            async with async_session_factory() as s: ...
    """

    __slots__ = ("_tenant_id", "_token")

    def __init__(self, tenant_id: UUID | None) -> None:
        self._tenant_id = tenant_id
        self._token: Token | None = None

    def __enter__(self) -> "tenant_scope":
        self._token = set_current_tenant(self._tenant_id)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            reset_current_tenant(self._token)
            self._token = None


def tenant_redis_key(*parts: str) -> str:
    """Build a Redis key namespaced by the current tenant.

    e.g. ``tenant_redis_key("working", session_id)`` → ``"<tenant_id>:working:<session_id>"``.
    Two inmobiliarias that happen to share a customer phone get isolated keys.
    """
    prefix = str(resolve_tenant_id())
    return ":".join((prefix, *parts))
