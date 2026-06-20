"""Add ambientes column to properties (Plan 28)

Revision ID: 0024_ambientes
Revises: 0023_avatar_photo
Create Date: 2026-06-20

Adds:
  - Column: properties.ambientes INTEGER NULL
    Total de espacios habitables (AR convention): 1 = monoambiente (0 dormitorios),
    2 = 1 dormitorio, 3 = 2 dormitorios, etc.
  Backfill: ambientes = CASE WHEN bedrooms = 0 THEN 1 ELSE bedrooms + 1 END
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_ambientes"
down_revision: str | None = "0023_avatar_photo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "ambientes",
            sa.Integer(),
            nullable=True,
            comment="Total de espacios habitables (AR): 1=monoambiente, 2=1dorm, etc.",
        ),
    )
    op.execute(
        """
        UPDATE properties
        SET ambientes = CASE
            WHEN bedrooms IS NULL THEN NULL
            WHEN bedrooms = 0 THEN 1
            ELSE bedrooms + 1
        END
        """
    )


def downgrade() -> None:
    op.drop_column("properties", "ambientes")
