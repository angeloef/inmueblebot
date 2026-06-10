"""notifications: add tenant_id column + RLS

Revision ID: 0005_notifications_tenant_id
Revises: 0004_auth_billing
Create Date: 2026-06-10

Add tenant_id to the notifications table so each inmobiliaria only sees its
own notifications. Mirrors the exact RLS/FK/index pattern from 0002_multitenancy.

IDEMPOTENT: all DDL uses IF [NOT] EXISTS and catalog guards.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_notifications_tenant_id"
down_revision: str | None = "0004_auth_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # 1) Add column (nullable first for backfill safety)
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS tenant_id UUID")

    # 2) Set server default to the default tenant
    op.execute(
        f"ALTER TABLE notifications ALTER COLUMN tenant_id "
        f"SET DEFAULT '{DEFAULT_TENANT_ID}'::uuid"
    )

    # 3) Backfill existing rows
    op.execute(
        f"UPDATE notifications SET tenant_id = '{DEFAULT_TENANT_ID}'::uuid "
        f"WHERE tenant_id IS NULL"
    )

    # 4) Enforce NOT NULL now that backfill is done
    op.execute("ALTER TABLE notifications ALTER COLUMN tenant_id SET NOT NULL")

    # 5) FK → tenants (guarded — no ADD CONSTRAINT IF NOT EXISTS in PG)
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_notifications_tenant_id_tenants'
            ) THEN
                ALTER TABLE notifications
                    ADD CONSTRAINT fk_notifications_tenant_id_tenants
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )

    # 6) Composite index for dashboard hot-path (tenant + recency)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_tenant_created "
        "ON notifications (tenant_id, created_at DESC)"
    )

    # 7) Row-Level Security — mirrors 0002_multitenancy exactly
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_notifications ON notifications")
    op.execute(
        """
        CREATE POLICY tenant_isolation_notifications ON notifications
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_notifications ON notifications")
    op.execute("ALTER TABLE notifications DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP INDEX IF EXISTS ix_notifications_tenant_created"
    )
    op.execute(
        "ALTER TABLE notifications "
        "DROP CONSTRAINT IF EXISTS fk_notifications_tenant_id_tenants"
    )
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS tenant_id")
