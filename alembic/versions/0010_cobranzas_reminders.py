"""cobranzas_reminders: per-stage payment reminders + contract expiry/IPC alert markers

Adds idempotency markers for the cobranzas notification jobs (Profesional 🔜):
  - charges.reminder_stages  (JSONB): which payment reminders fired (pre/due/overdue).
  - contracts.expiry_alert_sent_at: when the 30-day "contract expiring" alert was sent.
  - contracts.ipc_alert_for: the IPC adjustment period already alerted (per-cycle dedup).

Revision ID: 0010_cobranzas_reminders
Revises: 0009_appt_reminder_at
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_cobranzas_reminders"
down_revision: str | None = "0009_appt_reminder_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "charges",
        sa.Column("reminder_stages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column("expiry_alert_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column("ipc_alert_for", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contracts", "ipc_alert_for")
    op.drop_column("contracts", "expiry_alert_sent_at")
    op.drop_column("charges", "reminder_stages")
