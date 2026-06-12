"""appointment_reminder_sent_at: add reminder_sent_at to appointments (visit reminder job)

Idempotency marker for the 24h-before visit-reminder job (Profesional 🔜). NULL = the
reminder has not been sent/queued yet.

Revision ID: 0009_appt_reminder_at
Revises: 0008_property_reference_points
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_appt_reminder_at"
down_revision: str | None = "0008_property_reference_points"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "reminder_sent_at")
