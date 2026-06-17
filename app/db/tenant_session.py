"""Transaction-scoped tenant GUC — the wiring that drives Postgres RLS (V3 Phase 1).

Every SQLAlchemy transaction (sync or async, ``get_db`` or ad-hoc ``async_session_factory``)
must announce its tenant to Postgres via ``set_config('app.current_tenant_id', …, true)``
so RLS policies (``tenant_id = current_setting('app.current_tenant_id', true)::uuid``)
filter rows. The ``true`` third arg makes it *transaction-local*, so it cannot leak to the
next request on a pooled connection.

We attach ONE global ``after_begin`` listener on the SQLAlchemy ``Session`` class. That
fires for every session in the process — including the AsyncSession's inner sync Session
and the ad-hoc sessions that bypass ``get_db`` — so there is no callsite we can forget.

The tenant id comes from ``resolve_tenant_id()`` (the ContextVar), which falls back to the
default tenant when unset — keeping V2 / cron / ad-hoc paths working unchanged.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.tenancy import is_superadmin_context, resolve_tenant_id

_listener_installed = False

# Compiled via SQLAlchemy so the paramstyle is correct for BOTH backends sharing this one
# global listener: psycopg2 (%s, sync dashboard sessions) and asyncpg ($1, the bot).
_SET_TENANT_SQL = text("SELECT set_config('app.current_tenant_id', :tid, true)")
# Cross-tenant super-admin flag (transaction-local). 'on' ⇒ RLS exposes every tenant.
# Always written ('on'/'off') so a pooled connection never inherits a stale 'on'.
_SET_SUPERADMIN_SQL = text("SELECT set_config('app.is_superadmin', :flag, true)")


def install_tenant_guc_listener() -> None:
    """Install the global ``after_begin`` listener (idempotent)."""
    global _listener_installed
    if _listener_installed:
        return

    @event.listens_for(Session, "after_begin")
    def _set_tenant_guc(session, transaction, connection) -> None:  # noqa: ANN001
        # Only meaningful on PostgreSQL (set_config). Skip silently on sqlite/test engines.
        if connection.dialect.name != "postgresql":
            return
        try:
            tenant_id = resolve_tenant_id()
            connection.execute(_SET_TENANT_SQL, {"tid": str(tenant_id)})
            # Mirror the super-admin ContextVar onto a transaction-local GUC. Written on
            # EVERY begin (not only when on) so the previous request's 'on' can never leak
            # to the next checkout on a pooled connection.
            flag = "on" if is_superadmin_context() else "off"
            connection.execute(_SET_SUPERADMIN_SQL, {"flag": flag})
        except Exception as exc:  # pragma: no cover - defensive; never break a txn
            logger.warning(f"[Tenancy] could not set tenant GUC: {exc}")

    _listener_installed = True
