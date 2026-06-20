"""merge heads 0022 and 0024

Revision ID: 0025_merge_heads
Revises: 0022_sales_inquiries, 0024_ambientes
Create Date: 2026-06-20

"""
from alembic import op

revision: str = "0025_merge_heads"
down_revision: tuple = ("0022_sales_inquiries", "0024_ambientes")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
