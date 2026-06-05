"""pgvector + knowledge_chunks table (Phase 5 RAG)

Revision ID: 0003_pgvector_knowledge
Revises: 0002_multitenancy
Create Date: 2026-06-04

Adds:
  1. PostgreSQL extension: vector (pgvector)  — shared on the DB instance; idempotent.
  2. Table: knowledge_chunks — per-tenant embedding store for FAQ entries and property
     descriptions. Used by the V3 RAG layer (app/routers/v3/knowledge/).

Notes for the owner:
  - pgvector is available on all Render Postgres instances (no extra setup needed).
  - An IVFFlat index is created with lists=10 (suitable for up to ~300 chunks).
    When the table grows past ~1 000 rows, recreate it CONCURRENTLY with more lists:
        CREATE INDEX CONCURRENTLY ix_knowledge_chunks_ivfflat
        ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    Then drop the old index.
  - The migration is IDEMPOTENT: IF NOT EXISTS guards on every DDL statement.

Rollback (downgrade) drops the knowledge_chunks table; it does NOT uninstall the
vector extension (removing it would break other users of the extension on the same
cluster; the DBA can remove it manually if needed).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_pgvector_knowledge"
down_revision: str | None = "0002_multitenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Create knowledge_chunks table
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id          BIGSERIAL PRIMARY KEY,
            tenant_id   UUID NOT NULL,
            source_type VARCHAR(20) NOT NULL,
            source_id   BIGINT NOT NULL,
            chunk_text  TEXT NOT NULL,
            embedding   VECTOR(1536),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            CONSTRAINT fk_kc_tenant FOREIGN KEY (tenant_id)
                REFERENCES tenants(id) ON DELETE CASCADE,

            CONSTRAINT uq_kc_tenant_source
                UNIQUE (tenant_id, source_type, source_id)
        )
    """)

    # 3. tenant_id index for fast tenant-scoped scans
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_tenant_id
        ON knowledge_chunks (tenant_id)
    """)

    # 4. IVFFlat cosine index (lists=10 — good for tables up to ~300 rows)
    #    Wrapped in a DO block so it's a no-op if the index already exists.
    #    Note: Cannot use CONCURRENTLY inside a transaction — using regular CREATE.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'knowledge_chunks'
                  AND indexname = 'ix_knowledge_chunks_ivfflat'
            ) THEN
                CREATE INDEX ix_knowledge_chunks_ivfflat
                ON knowledge_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 10);
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
    # intentionally NOT dropping the vector extension
