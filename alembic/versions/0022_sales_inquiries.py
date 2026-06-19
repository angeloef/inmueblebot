"""sales_inquiries table (Plan 20 — Enterprise contact form)

Revision ID: 0022_sales_inquiries
Revises: 0021_avatar_color
Create Date: 2026-06-19

Adds:
  - Table: sales_inquiries — consultas Enterprise enviadas desde la app.
    Global (NO RLS, como error_reports): solo super-admin la lee.

Notes:
  - IDEMPOTENT: IF NOT EXISTS guards on all DDL.
  - Rollback drops the table with CASCADE.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_sales_inquiries"
down_revision: str | None = "0021_avatar_color"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sales_inquiries (
            id             UUID PRIMARY KEY,
            tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            account_id     UUID,
            contact_name   VARCHAR(255) NOT NULL,
            contact_email  VARCHAR(255),
            phone          VARCHAR(50),
            property_count VARCHAR(50),
            message        TEXT,
            status         VARCHAR(20) NOT NULL DEFAULT 'open',
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sales_inquiries_tenant_id "
        "ON sales_inquiries (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sales_inquiries_status_created_at "
        "ON sales_inquiries (status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sales_inquiries CASCADE")
