"""tenant_accounts + subscriptions tables (Phase 1 auth/billing)

Revision ID: 0004_auth_billing
Revises: 0003_pgvector_knowledge
Create Date: 2026-06-09

Adds:
  1. Table: tenant_accounts — email/password logins for each inmobiliaria.
     Global (no RLS). Unique index on email; index on tenant_id.
  2. Table: subscriptions — MercadoPago subscription state per tenant.
     Global (no RLS). Unique index on mp_preapproval_id; index on tenant_id.

Notes:
  - Both tables reference tenants(id) with ON DELETE CASCADE.
  - Migration is IDEMPOTENT: IF NOT EXISTS guards on all DDL.

Rollback (downgrade) drops both tables with CASCADE.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004_auth_billing"
down_revision: str | None = "0003_pgvector_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_accounts (
            id              UUID PRIMARY KEY,
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email           VARCHAR(255) NOT NULL,
            password_hash   VARCHAR(255) NOT NULL,
            full_name       VARCHAR(200),
            role            VARCHAR(20) NOT NULL DEFAULT 'owner',
            email_verified_at TIMESTAMPTZ,
            token_version   INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tenant_accounts_email "
        "ON tenant_accounts (email)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenant_accounts_tenant_id "
        "ON tenant_accounts (tenant_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id                 UUID PRIMARY KEY,
            tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            provider           VARCHAR(40) NOT NULL DEFAULT 'mercadopago',
            mp_preapproval_id  VARCHAR(64),
            mp_payer_id        VARCHAR(64),
            status             VARCHAR(20) NOT NULL DEFAULT 'trial',
            plan               VARCHAR(40),
            amount             NUMERIC(12,2),
            currency           VARCHAR(3) NOT NULL DEFAULT 'ARS',
            trial_ends_at      TIMESTAMPTZ,
            current_period_end TIMESTAMPTZ,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_mp_preapproval_id "
        "ON subscriptions (mp_preapproval_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_tenant_id "
        "ON subscriptions (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS tenant_accounts CASCADE")
