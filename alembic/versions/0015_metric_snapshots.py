"""metric_snapshots: snapshot mensual de KPIs por sucursal (Enterprise)

Revision ID: 0015_metric_snapshots
Revises: 0014_documents
Create Date: 2026-06-13

Tabla ``metric_snapshots`` (JSONB por (tenant, mes)) con RLS **org-aware** (mismo predicado
que 0013): el GUC=org ve los snapshots de todas sus sucursales (consolidado/comparativa);
el GUC=sucursal queda aislado.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_metric_snapshots"
down_revision: str | None = "0014_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "current_setting('app.current_tenant_id', true)::uuid"
_PREDICATE = (
    f"(tenant_id = {_GUC} "
    f"OR tenant_id IN (SELECT id FROM tenants WHERE parent_tenant_id = {_GUC}))"
)


def upgrade() -> None:
    op.create_table(
        "metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                                name="fk_metric_snapshots_tenant_id_tenants"),
    )
    op.create_index("ix_metric_snapshots_tenant_id", "metric_snapshots", ["tenant_id"])
    op.create_index("uq_metric_snapshots_tenant_period", "metric_snapshots",
                    ["tenant_id", "period"], unique=True)

    op.execute("ALTER TABLE metric_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE metric_snapshots FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_metric_snapshots ON metric_snapshots")
    op.execute(
        f"CREATE POLICY tenant_isolation_metric_snapshots ON metric_snapshots "
        f"USING {_PREDICATE} WITH CHECK {_PREDICATE}"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_metric_snapshots ON metric_snapshots")
    op.execute("DROP TABLE IF EXISTS metric_snapshots")
