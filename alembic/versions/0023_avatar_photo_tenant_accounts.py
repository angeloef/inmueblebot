"""avatar_photo column on tenant_accounts (Plan 26 — avatar con foto)

Revision ID: 0023_avatar_photo
Revises: 0022_sales_inquiries
Create Date: 2026-06-20

Adds:
  - Column: tenant_accounts.avatar_photo TEXT NULL
    Stores a base64-encoded cropped circular avatar image per account.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_avatar_photo"
down_revision: str | None = "0021_avatar_color"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenant_accounts
        ADD COLUMN IF NOT EXISTS avatar_photo TEXT NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tenant_accounts DROP COLUMN IF EXISTS avatar_photo")
