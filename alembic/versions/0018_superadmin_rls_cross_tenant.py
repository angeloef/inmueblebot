"""super-admin cross-tenant RLS (plan 04)

Revision ID: 0018_superadmin_rls_cross_tenant
Revises: 0017_search_failures_unique
Create Date: 2026-06-16

Add a controlled cross-tenant escape hatch for the super-admin surface (/superadmin,
planes 05/06/07) WITHOUT touching DB roles or using BYPASSRLS.

Every tenant-isolation policy is rewritten to also pass when a transaction-local GUC
``app.is_superadmin`` is ``'on'``:

    current_setting('app.is_superadmin', true) = 'on'
    OR col = current_tenant
    OR col IN (SELECT id FROM tenants WHERE parent_tenant_id = current_tenant)

Effect:
  - GUC off / absent (every normal request, bot, cron) → NULL-safe ⇒ the super-admin
    clause is false ⇒ org-aware isolation is IDENTICAL to before (planes 0002/0013/0014/0015).
  - GUC = 'on' (only inside ``require_superadmin`` → ``set_superadmin(True)`` → the
    session listener writes the GUC) ⇒ the policy passes for EVERY row ⇒ the super-admin
    can read and (WITH CHECK) write rows of any inmobiliaria in one session.

Fail-closed & leak-proof: the GUC is transaction-local (``set_config(..., true)``) and
written on every transaction begin ('on'/'off'), so it can never leak to the next checkout
on a pooled connection. ``current_setting(..., true)`` is NULL-safe.

IDEMPOTENT: DROP POLICY IF EXISTS + catalog guards ⇒ safe on fresh-db, prod, and re-run.
"""
from collections.abc import Sequence

from sqlalchemy import inspect

from alembic import op

revision: str = "0018_superadmin_rls_cross_tenant"
down_revision: str | None = "0017_search_failures_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> (agency FK column, policy name). The complete set of tenant-isolation policies
# created across 0002 (SCOPED_COLUMNS), 0005 (notifications), 0012 (site briefs), 0014
# (documents) y 0015 (metric_snapshots). Duplicated here so the migration does not depend
# on app import state.
TENANT_POLICIES: dict[str, tuple[str, str]] = {
    "users": ("tenant_id", "tenant_isolation_users"),
    "properties": ("tenant_id", "tenant_isolation_properties"),
    "conversations": ("tenant_id", "tenant_isolation_conversations"),
    "messages": ("tenant_id", "tenant_isolation_messages"),
    "appointments": ("tenant_id", "tenant_isolation_appointments"),
    "faq_entries": ("tenant_id", "tenant_isolation_faq_entries"),
    "user_episodes": ("tenant_id", "tenant_isolation_user_episodes"),
    "zone_stats": ("tenant_id", "tenant_isolation_zone_stats"),
    "search_failures": ("tenant_id", "tenant_isolation_search_failures"),
    "contracts": ("org_id", "tenant_isolation_contracts"),
    "charges": ("tenant_id", "tenant_isolation_charges"),
    "contract_expenses": ("tenant_id", "tenant_isolation_contract_expenses"),
    "notifications": ("tenant_id", "tenant_isolation_notifications"),
    "tenant_site_briefs": ("tenant_id", "tenant_isolation_site_briefs"),
    "documents": ("tenant_id", "tenant_isolation_documents"),
    "metric_snapshots": ("tenant_id", "tenant_isolation_metric_snapshots"),
}

_GUC = "current_setting('app.current_tenant_id', true)::uuid"
_SUPERADMIN = "current_setting('app.is_superadmin', true) = 'on'"


def _org_aware_predicate(col: str) -> str:
    """The pre-0018 org-aware isolation predicate (used by downgrade)."""
    return (
        f"({col} = {_GUC} "
        f"OR {col} IN (SELECT id FROM tenants WHERE parent_tenant_id = {_GUC}))"
    )


def _superadmin_predicate(col: str) -> str:
    """Org-aware isolation OR cross-tenant super-admin escape hatch."""
    return (
        f"({_SUPERADMIN} "
        f"OR {col} = {_GUC} "
        f"OR {col} IN (SELECT id FROM tenants WHERE parent_tenant_id = {_GUC}))"
    )


def _rewrite_policies(predicate_fn) -> None:  # noqa: ANN001
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    for table, (col, policy) in TENANT_POLICIES.items():
        if table not in existing_tables:
            continue
        predicate = predicate_fn(col)
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"USING {predicate} WITH CHECK {predicate}"
        )


def upgrade() -> None:
    _rewrite_policies(_superadmin_predicate)


def downgrade() -> None:
    _rewrite_policies(_org_aware_predicate)
