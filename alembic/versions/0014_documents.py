"""documents: archivos adjuntos a clientes/contratos (Enterprise)

Revision ID: 0014_documents
Revises: 0013_branch_subtenant_org_rls
Create Date: 2026-06-13

Tabla ``documents`` (DNI, recibos, contratos firmados, garantías) guardados como base64.
Tenant-scoped con RLS **org-aware** (mismo predicado que 0013): el GUC=org ve/escribe los
documentos de todas sus sucursales; el GUC=sucursal queda aislado.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_documents"
down_revision: str | None = "0013_branch_subtenant_org_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "current_setting('app.current_tenant_id', true)::uuid"
_PREDICATE = (
    f"(tenant_id = {_GUC} "
    f"OR tenant_id IN (SELECT id FROM tenants WHERE parent_tenant_id = {_GUC}))"
)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                                name="fk_documents_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_documents_client_id_users"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE",
                                name="fk_documents_contract_id_contracts"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_client_id", "documents", ["client_id"])
    op.create_index("ix_documents_contract_id", "documents", ["contract_id"])

    # RLS org-aware (mirror 0013).
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_documents ON documents")
    op.execute(
        f"CREATE POLICY tenant_isolation_documents ON documents "
        f"USING {_PREDICATE} WITH CHECK {_PREDICATE}"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_documents ON documents")
    op.execute("DROP TABLE IF EXISTS documents")
