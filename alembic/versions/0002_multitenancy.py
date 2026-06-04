"""multi-tenancy foundation (Phase 1)

Revision ID: 0002_multitenancy
Revises: 0001_baseline
Create Date: 2026-06-04

Introduce true tenant isolation while V2 keeps serving the default tenant.

IDEMPOTENT BY DESIGN. The 0001 baseline is metadata-driven (`create_all`), so on a FRESH
db it already creates the current models — including the new tenant columns/tables. On
EXISTING prod those don't exist yet. To work on both, every statement here uses
`IF [NOT] EXISTS` / catalog guards, so it's safe on a fresh db, on prod, and on re-run.

V2 safety (bulletproof default-tenant fallback):
  - Every scoped column gets a SERVER DEFAULT = the default tenant. V2 INSERTs that omit
    `tenant_id` therefore still produce a valid, RLS-passing row (it equals the GUC, which
    `resolve_tenant_id()` also defaults to). No V2 code change required.
  - RLS is ENABLED as a safety net. The policy is NULL-safe (`current_setting(..., true)`).
    NOTE (owner): RLS only constrains a NON-owner app role. If the app connects as the table
    owner, add `FORCE ROW LEVEL SECURITY` (or use a dedicated app role). App-layer scoping is
    the primary wall; RLS is the net. Never run the app as BYPASSRLS.

Zero-downtime on LARGE prod tables (owner step, outside this migration's single txn):
  prefer `CREATE INDEX CONCURRENTLY`, batched backfill, and `ADD CONSTRAINT NOT VALID` →
  `VALIDATE CONSTRAINT` → `SET NOT NULL`. The straightforward DDL below is correct for a
  fresh db / clone and small tables; verify on a prod clone before running on prod.
"""
from collections.abc import Sequence

from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_multitenancy"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with settings.DEFAULT_TENANT_ID and the seeded tenants row.
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# table -> agency FK column (mirror of app.core.tenancy; duplicated so the migration does
# not depend on app import state). contracts uses org_id (tenant_id there = renter).
SCOPED_COLUMNS: dict[str, str] = {
    "users": "tenant_id",
    "properties": "tenant_id",
    "conversations": "tenant_id",
    "messages": "tenant_id",
    "appointments": "tenant_id",
    "faq_entries": "tenant_id",
    "user_episodes": "tenant_id",
    "zone_stats": "tenant_id",
    "search_failures": "tenant_id",
    "contracts": "org_id",
    "charges": "tenant_id",
    "contract_expenses": "tenant_id",
}

# Naive-timestamp columns to convert to TIMESTAMPTZ (interpreted as UTC).
TIMESTAMPTZ_FIXUPS: list[tuple[str, str]] = [
    ("user_episodes", "created_at"),
    ("search_failures", "last_failed_at"),
]


def _create_tenant_tables() -> None:
    """Create tenants + tenant_settings (checkfirst — no-op if 0001 already made them)."""
    import app.db.models  # noqa: F401  (registers all tables on Base.metadata)
    from app.db.base import Base
    from app.db.models.tenant import Tenant, TenantSettings

    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Tenant.__table__, TenantSettings.__table__],
        checkfirst=True,
    )


def _seed_default_tenant() -> None:
    op.execute(
        f"""
        INSERT INTO tenants (id, slug, display_name, company_name, timezone, status, created_at)
        VALUES (
            '{DEFAULT_TENANT_ID}', 'default', 'Inmobiliaria (default)',
            'Inmobiliaria (default)', 'America/Argentina/Cordoba', 'active', now()
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    _create_tenant_tables()
    _seed_default_tenant()

    for table, col in SCOPED_COLUMNS.items():
        if table not in existing_tables:
            # Fresh-db edge: 0001 didn't create it (shouldn't happen) — skip safely.
            continue

        # 1) add nullable agency FK column with a server default = default tenant.
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} UUID")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT '{DEFAULT_TENANT_ID}'::uuid"
        )

        # 2) FK → tenants (guarded — no ADD CONSTRAINT IF NOT EXISTS in PG).
        fk_name = f"fk_{table}_{col}_tenants"
        op.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{fk_name}'
                ) THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT {fk_name}
                        FOREIGN KEY ({col}) REFERENCES tenants(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )

        # 3) index on the agency FK.
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})")

        # 4) backfill existing rows to the default tenant.
        #    (For very large prod tables do this in batches outside the migration.)
        op.execute(
            f"UPDATE {table} SET {col} = '{DEFAULT_TENANT_ID}'::uuid WHERE {col} IS NULL"
        )

    # Composite hot-path indexes.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversations_tenant_session "
        "ON conversations (tenant_id, session_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversations_tenant_user "
        "ON conversations (tenant_id, user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_messages_tenant_conversation "
        "ON messages (tenant_id, conversation_id)"
    )

    # zone_stats: zone_name is no longer globally unique — uniqueness is now per-tenant.
    op.execute("ALTER TABLE zone_stats DROP CONSTRAINT IF EXISTS uq_zone_stats_zone_name")
    op.execute("DROP INDEX IF EXISTS uq_zone_stats_zone_name")
    op.execute("DROP INDEX IF EXISTS ix_zone_stats_zone_name")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_zone_stats_tenant_zone "
        "ON zone_stats (tenant_id, zone_name)"
    )

    # TIMESTAMPTZ conversions (only if still naive — interpret stored values as UTC).
    for table, col in TIMESTAMPTZ_FIXUPS:
        if table not in existing_tables:
            continue
        op.execute(
            f"""
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{col}'
                      AND data_type = 'timestamp without time zone'
                ) THEN
                    ALTER TABLE {table}
                        ALTER COLUMN {col} TYPE TIMESTAMPTZ
                        USING {col} AT TIME ZONE 'UTC';
                    ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT now();
                END IF;
            END $$;
            """
        )

    # Row-Level Security (safety net). NULL-safe policy via current_setting(..., true).
    for table, col in SCOPED_COLUMNS.items():
        if table not in existing_tables:
            continue
        policy = f"tenant_isolation_{table}"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE so RLS binds even for the table OWNER. On Render the app connects as
        # inmueblebot_user, which OWNS these tables — without FORCE a table owner bypasses
        # RLS entirely. Safe here: the backfill above already ran (before this loop), and the
        # app/admin always set the tenant GUC via the session listener (default tenant when
        # unset), so existing default-tenant rows stay fully visible to V2.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"""
            CREATE POLICY {policy} ON {table}
            USING ({col} = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK ({col} = current_setting('app.current_tenant_id', true)::uuid)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    for table, col in SCOPED_COLUMNS.items():
        if table not in existing_tables:
            continue
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")

    op.execute("DROP INDEX IF EXISTS uq_zone_stats_tenant_zone")
    op.execute("DROP TABLE IF EXISTS tenant_settings")
    op.execute("DROP TABLE IF EXISTS tenants")
