"""baseline schema (Phase 0b)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-04

Adopt Alembic on an EXISTING, drifted database.

Why metadata-driven instead of hand-written op.create_table calls:
  The ORM models in `app.db.models` ALREADY reflect the reconciled, post-startup-migration
  schema (e.g. `properties.type`/`lat`/`lng`/`area_m2`, `images ARRAY(Text)`,
  `extra_data JSONB`, UUID PKs, TIMESTAMPTZ). The legacy `_run_startup_migration` existed
  only to drag old prod columns UP to match these models. So the models ARE the target
  schema — deriving the baseline from `Base.metadata` guarantees the migration and the ORM
  can never disagree (no hand-transcription drift across 13 tables).

`create_all(checkfirst=True)` (the default) only creates MISSING tables, so this migration is:
  - on EXISTING prod (tables present, drifted-but-aligned)  → effectively a no-op; it records
    the version without altering existing tables. Verify on a CLONE first.
  - on a FRESH db (dev / CI / clone)                        → creates the full correct schema.

It deliberately does NOT touch the unmanaged tables `bot_settings` / `leads` — they aren't in
`Base.metadata` (see `alembic/env.py` UNMANAGED_TABLES), so create_all/drop_all ignore them.

⚠️ VERIFICATION (owner step — needs a prod schema dump): diff this baseline against
`pg_dump --schema-only` of prod on a clone, and confirm `alembic upgrade head` (or
`alembic stamp head` on the already-populated prod DB) leaves the schema correct, BEFORE
flipping `RUN_LEGACY_STARTUP_MIGRATION=False`.
"""
from collections.abc import Sequence

from sqlalchemy import MetaData

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _metadata() -> MetaData:
    # Import the package so every model registers on the single Base.metadata
    # (unified in Phase 0a). Imported lazily so the module loads even outside an app ctx.
    import app.db.models  # noqa: F401  (side effect: registers all tables)
    from app.db.base import Base

    return Base.metadata


def upgrade() -> None:
    # checkfirst=True (default) → only creates tables missing from the target DB.
    _metadata().create_all(bind=op.get_bind())


def downgrade() -> None:
    _metadata().drop_all(bind=op.get_bind())
