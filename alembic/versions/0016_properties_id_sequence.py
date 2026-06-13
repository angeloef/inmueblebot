"""properties_id_sequence: global sequence for properties.id (multi-tenant safe)

Fixes a multi-tenant PK collision: properties.id was assigned in Python via
SELECT max(id)+1, but that query runs under Row-Level Security and only sees the
current tenant's rows. A new tenant's first property always computed id=1, which
collides with another tenant's existing id=1 (the PK is global, not per-tenant).

This migration introduces a real Postgres SEQUENCE (sequences are global, never
RLS-scoped) and wires it as the column default.

Seeding is RLS-aware: properties has FORCE ROW LEVEL SECURITY (migration 0002)
and Alembic does not set app.current_tenant_id, so a plain MAX(id) here would see
ZERO rows (GUC unset → policy matches nothing) and seed the sequence to 1 —
recreating the collision. We therefore DISABLE RLS only for the seed query so the
owner sees ALL tenants' rows, then ENABLE it again. DISABLE/ENABLE toggles
relrowsecurity only; the FORCE flag (relforcerowsecurity) persists untouched.

Revision ID: 0016_properties_id_sequence
Revises: 0015_metric_snapshots
Create Date: 2026-06-13
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0016_properties_id_sequence"
down_revision: str | None = "0015_metric_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS properties_id_seq")
    # Temporarily lift RLS so the owner sees every tenant's rows for the seed.
    op.execute("ALTER TABLE properties DISABLE ROW LEVEL SECURITY")
    # is_called=false → the NEXT nextval() returns global_max + 1.
    op.execute(
        "SELECT setval('properties_id_seq', "
        "COALESCE((SELECT MAX(id) FROM properties), 0) + 1, false)"
    )
    op.execute("ALTER TABLE properties ENABLE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE properties ALTER COLUMN id "
        "SET DEFAULT nextval('properties_id_seq')"
    )
    # Tie the sequence lifecycle to the column.
    op.execute("ALTER SEQUENCE properties_id_seq OWNED BY properties.id")


def downgrade() -> None:
    op.execute("ALTER TABLE properties ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS properties_id_seq")
