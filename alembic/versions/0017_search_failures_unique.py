"""search_failures unique index for upsert

Revision ID: 0017_search_failures_unique
Revises: 0016_properties_id_sequence
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "0017_search_failures_unique"
down_revision = "0016_properties_id_sequence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill NULL key columns to '' so the unique index can be built
    op.execute("UPDATE search_failures SET operation = '' WHERE operation IS NULL")
    op.execute("UPDATE search_failures SET property_type = '' WHERE property_type IS NULL")
    op.execute("UPDATE search_failures SET zone = '' WHERE zone IS NULL")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_search_failures_combo "
        "ON search_failures (tenant_id, operation, property_type, zone)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_search_failures_combo")
