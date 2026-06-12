"""cold_lead_marker: add cold_reengaged_at to users (cold-lead re-engagement job)

One-shot-per-cooling idempotency for the cold-lead job (Profesional 🔜): a lead is
re-engaged once per cooling period. If they reply (last_interaction advances past
cold_reengaged_at) and go cold again, they become eligible again.

Revision ID: 0011_cold_lead_marker
Revises: 0010_cobranzas_reminders
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_cold_lead_marker"
down_revision: str | None = "0010_cobranzas_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("cold_reengaged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "cold_reengaged_at")
