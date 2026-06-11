"""property_reference_points: add reference_points JSONB column to properties

Revision ID: 0008_property_reference_points
Revises: 0007_tenant_members
Create Date: 2026-06-11
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_property_reference_points"
down_revision: str | None = "0007_tenant_members"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "reference_points",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("properties", "reference_points")
