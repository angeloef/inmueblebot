"""error_reports table (Plan 07 — in-app error reporting + superadmin triage)

Revision ID: 0019_error_reports
Revises: 0018_superadmin_rls_cross_tenant
Create Date: 2026-06-17

Adds:
  - Table: error_reports — reportes de error enviados desde la app por usuarios.
    Global (NO RLS, igual que subscriptions): el triage lo hacen los super-admin
    cross-tenant. tenant_id queda para filtrar/atribuir.

Notes:
  - References tenants(id) with ON DELETE CASCADE.
  - Migration is IDEMPOTENT: IF NOT EXISTS guards on all DDL.

Rollback (downgrade) drops the table with CASCADE.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_error_reports"
down_revision: str | None = "0018_superadmin_rls_cross_tenant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS error_reports (
            id             UUID PRIMARY KEY,
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            account_id     UUID,
            reporter_email VARCHAR(255),
            message        TEXT NOT NULL,
            context        JSONB NOT NULL DEFAULT '{}',
            severity       VARCHAR(20) NOT NULL DEFAULT 'med',
            status         VARCHAR(20) NOT NULL DEFAULT 'open',
            triage_notes   TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_error_reports_tenant_id ON error_reports (tenant_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_error_reports_status_created_at "
        "ON error_reports (status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS error_reports CASCADE")
