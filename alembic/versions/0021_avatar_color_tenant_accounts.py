"""avatar_color column on tenant_accounts (Plan 16 — perfil de usuario)

Revision ID: 0021_avatar_color_tenant_accounts
Revises: 0020_property_import_requests
Create Date: 2026-06-19

Adds:
  - Column: tenant_accounts.avatar_color VARCHAR(20) NULL
    Stores the UI avatar color preference (navy/teal/violet/green/orange) per account.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_avatar_color_tenant_accounts"
down_revision: str | None = "0020_property_import_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenant_accounts
        ADD COLUMN IF NOT EXISTS avatar_color VARCHAR(20) NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_accounts DROP COLUMN IF EXISTS avatar_color")
