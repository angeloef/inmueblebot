"""Snapshot mensual de KPIs por tenant (sucursal) — reportes ejecutivos Enterprise.

Un job guarda cada mes una 'foto' de las métricas de cada sucursal (leaf tenant) en esta
tabla. Las tendencias mes-a-mes quedan estables y baratas aunque los datos cambien después.
El blob ``metrics`` es JSONB para que el catálogo de métricas crezca sin migraciones.

RLS org-aware (migración 0015): el dueño (GUC=org) ve los snapshots de todas sus sucursales
→ consolidado + comparativa; cada sucursal ve solo el suyo.
"""
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="FK al tenant (sucursal/inmobiliaria)",
    )
    # Primer día del mes que resume (p.ej. 2026-05-01 = métricas de mayo 2026).
    period: Mapped[date] = mapped_column(Date, nullable=False, comment="Primer día del mes")

    # Blob con los grupos de métricas (funnel/cobranzas/cartera/demanda).
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("uq_metric_snapshots_tenant_period", "tenant_id", "period", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MetricSnapshot(tenant_id={self.tenant_id}, period={self.period})>"
