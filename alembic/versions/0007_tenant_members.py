"""tenant_members: team/seats — invitar usuarios a una inmobiliaria existente

Revision ID: 0007_tenant_members
Revises: 0006_google_oauth
Create Date: 2026-06-11
"""
from collections.abc import Sequence
from alembic import op

revision: str = "0007_tenant_members"
down_revision: str | None = "0006_google_oauth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            name VARCHAR(200),
            avatar_color VARCHAR(20),
            photo_url TEXT,
            description VARCHAR(255),
            is_admin BOOLEAN NOT NULL DEFAULT false,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            invite_token VARCHAR(100),
            invite_expires_at TIMESTAMPTZ,
            account_id UUID REFERENCES tenant_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_members_tenant_id "
        "ON tenant_members (tenant_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_members_tenant_email "
        "ON tenant_members (tenant_id, email)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_members_invite_token "
        "ON tenant_members (invite_token) WHERE invite_token IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_members")
