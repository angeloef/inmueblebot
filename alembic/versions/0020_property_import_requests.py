"""property_import_requests + property_import_files (Plan 15 — importación asistida)

Revision ID: 0020_property_import_requests
Revises: 0019_error_reports
Create Date: 2026-06-18

Adds:
  - Table: property_import_requests — pedido de carga asistida de propiedades.
    Global (NO RLS, igual que error_reports). El cliente crea; los devs gestionan.
  - Table: property_import_files — archivos adjuntos (base64) de cada pedido.

Notes:
  - Ambas tablas referencian tenants(id) / property_import_requests(id) con CASCADE.
  - Migration is IDEMPOTENT: IF NOT EXISTS guards on all DDL.

Rollback (downgrade) drops ambas tablas con CASCADE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_property_import_requests"
down_revision: str | None = "0019_error_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS property_import_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            account_id      UUID,
            requester_email VARCHAR(255) NOT NULL,
            note            TEXT,
            status          VARCHAR(20) NOT NULL DEFAULT 'received',
            item_count_estimate INTEGER,
            admin_notes     TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_property_import_requests_tenant_id"
        " ON property_import_requests(tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_property_import_requests_status_created"
        " ON property_import_requests(status, created_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS property_import_files (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            import_request_id   UUID NOT NULL
                REFERENCES property_import_requests(id) ON DELETE CASCADE,
            filename            VARCHAR(255) NOT NULL,
            content_type        VARCHAR(100) NOT NULL,
            size_bytes          INTEGER NOT NULL DEFAULT 0,
            data                TEXT NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_property_import_files_request_id
            ON property_import_files(import_request_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS property_import_files CASCADE;")
    op.execute("DROP TABLE IF EXISTS property_import_requests CASCADE;")
