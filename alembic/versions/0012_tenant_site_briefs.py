"""tenant_site_briefs: per-tenant website intake brief (Profesional 🔜 — sitio web Fase A)

One brief per inmobiliaria capturing brand/pitch/contact/domain/design/catalog so the
founder can build the public site manually. RLS-scoped per tenant (mirrors 0005).

Revision ID: 0012_tenant_site_briefs
Revises: 0011_cold_lead_marker
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_tenant_site_briefs"
down_revision: str | None = "0011_cold_lead_marker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_site_briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("brand", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pitch", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("contact", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("domain", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("design", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("catalog", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name="fk_site_briefs_tenant_id_tenants",
        ),
    )
    op.create_index("uq_site_briefs_tenant", "tenant_site_briefs", ["tenant_id"], unique=True)

    # Row-Level Security — mirrors 0005_notifications_tenant_id.
    op.execute("ALTER TABLE tenant_site_briefs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_site_briefs FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_site_briefs ON tenant_site_briefs")
    op.execute(
        """
        CREATE POLICY tenant_isolation_site_briefs ON tenant_site_briefs
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_site_briefs ON tenant_site_briefs")
    op.execute("ALTER TABLE tenant_site_briefs DISABLE ROW LEVEL SECURITY")
    op.drop_index("uq_site_briefs_tenant", table_name="tenant_site_briefs")
    op.drop_table("tenant_site_briefs")
