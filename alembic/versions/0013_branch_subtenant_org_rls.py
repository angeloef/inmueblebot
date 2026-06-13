"""multi-sucursal (Enterprise): branch = sub-tenant + org-aware RLS

Revision ID: 0013_branch_subtenant_org_rls
Revises: 0012_tenant_site_briefs
Create Date: 2026-06-13

Enterprise multi-sucursal, Camino A (sucursal = sub-tenant). Two changes:

1) ``tenants.parent_tenant_id`` (nullable FK → tenants). NULL = tenant raíz (org Enterprise
   o inmobiliaria standalone). Si está seteado, el tenant es una SUCURSAL cuyo dueño/org es
   ``parent_tenant_id``. Cada sucursal tiene su propio número Meta; la org padre no.

2) **Org-aware RLS**: cada política de aislamiento por tenant se reescribe para que el GUC
   ``app.current_tenant_id`` también dé acceso a las filas de las sucursales hijas:

       col = current_tenant  OR  col IN (SELECT id FROM tenants WHERE parent_tenant_id = current_tenant)

   Efecto:
   - GUC = sucursal (hija/standalone) → la subconsulta no devuelve hijos → ve SOLO sus filas
     (aislamiento idéntico al actual). Gerente de sucursal y bot por número quedan iguales.
   - GUC = org (padre con hijos) → ve y ESCRIBE filas de TODAS sus sucursales en una sola
     sesión → habilita el dashboard consolidado y la reasignación cross-sucursal (mover una
     propiedad de la sucursal A a la B = UPDATE tenant_id, permitido por el WITH CHECK).
   - Tenants sin hijos (obera/default) → comportamiento idéntico al anterior.

IDEMPOTENT: usa IF [NOT] EXISTS / DROP POLICY IF EXISTS, seguro en fresh-db, prod y re-run.
Fail-closed: ``current_setting(..., true)`` es NULL-safe; GUC ausente ⇒ NULL ⇒ 0 filas.
"""
from collections.abc import Sequence

from sqlalchemy import inspect

from alembic import op

revision: str = "0013_branch_subtenant_org_rls"
down_revision: str | None = "0012_tenant_site_briefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> (agency FK column, policy name). Mirror of every tenant-scoped policy created in
# 0002 (SCOPED_COLUMNS), 0005 (notifications) y 0012 (tenant_site_briefs). Duplicado acá para
# no depender del estado de import de la app.
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
}

# Plain tenant-isolation policy (the pre-0013 form). Used by downgrade().
_GUC = "current_setting('app.current_tenant_id', true)::uuid"


def _org_aware_predicate(col: str) -> str:
    return (
        f"({col} = {_GUC} "
        f"OR {col} IN (SELECT id FROM tenants WHERE parent_tenant_id = {_GUC}))"
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1) tenants.parent_tenant_id (self-FK, nullable, RESTRICT so a populated org can't be
    #    deleted out from under its branches). Index for the children subquery.
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS parent_tenant_id UUID")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_tenants_parent_tenant_id'
            ) THEN
                ALTER TABLE tenants
                    ADD CONSTRAINT fk_tenants_parent_tenant_id
                    FOREIGN KEY (parent_tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenants_parent_tenant_id "
        "ON tenants (parent_tenant_id)"
    )

    # 2) Rewrite every tenant-isolation policy to the org-aware form.
    for table, (col, policy) in TENANT_POLICIES.items():
        if table not in existing_tables:
            continue
        predicate = _org_aware_predicate(col)
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"USING {predicate} WITH CHECK {predicate}"
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    # Restore the plain (non-org-aware) tenant-isolation policies.
    for table, (col, policy) in TENANT_POLICIES.items():
        if table not in existing_tables:
            continue
        predicate = f"({col} = {_GUC})"
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} "
            f"USING {predicate} WITH CHECK {predicate}"
        )

    op.execute("DROP INDEX IF EXISTS ix_tenants_parent_tenant_id")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS fk_tenants_parent_tenant_id")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS parent_tenant_id")
