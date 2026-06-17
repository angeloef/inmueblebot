"""
Modelos de operaciones inmobiliarias (fase crítica del plan
ImplementacionesWIP/04_gestion-operaciones-inmobiliarias.md).

Promueve las relaciones cliente↔propiedad de blobs JSONB (users.extra_data) a
tablas relacionales con FK e historial, y agrega las entidades que una
inmobiliaria real necesita: garantes y ventas. La atribución por agente
(``agent_id``) referencia a ``tenant_members``.

Las tablas se crean de forma idempotente en ``ensure_operations_schema``
(app/api/routes/operations.py), en transacción aislada — NO en la migración
monolítica de admin.py (ver memoria startup-migration-single-txn-landmine).
"""
from datetime import datetime, date
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    String, Integer, BigInteger, Float, Date, DateTime, ForeignKey, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PropertyRelation(Base):
    """Vínculo cliente↔propiedad (comprador/inquilino/interesado/propietario).

    Reemplaza el array JSONB ``users.extra_data.property_relations`` y los punteros
    ``properties.extra_data.buyer_id/tenant_id`` por filas con FK. Permite múltiples
    clientes por propiedad (co-inquilinos) e historial (status active|ended).
    """
    __tablename__ = "property_relations"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True, comment="FK al tenant/inmobiliaria (RLS)",
    )
    property_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False,
    )
    client_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    relation: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="buyer | tenant | interested | owner",
    )
    agent_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_members.id", ondelete="SET NULL"),
        nullable=True, comment="Agente (tenant_members) atribuido",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active", comment="active | ended",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_property_relations_property", "tenant_id", "property_id"),
        Index("ix_property_relations_client", "tenant_id", "client_id"),
    )


class Guarantor(Base):
    """Garante de un contrato de alquiler (garantía propietaria, recibo, caución, otro)."""
    __tablename__ = "guarantors"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    contract_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=True,
    )
    client_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="Opcional: si el garante también es un cliente del sistema",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    guarantee_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="otro",
        comment="propietaria | recibo | caucion | otro",
    )
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    guarantee_property_address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_guarantors_contract", "tenant_id", "contract_id"),
    )


class Sale(Base):
    """Operación de venta de una propiedad (seña/reserva → firma → cierre)."""
    __tablename__ = "sales"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True,
    )
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("properties.id", ondelete="SET NULL"), nullable=True,
    )
    buyer_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    seller_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        comment="Propietario vendedor",
    )
    agent_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_members.id", ondelete="SET NULL"), nullable=True,
    )
    sale_price: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    reservation_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    reservation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    commission_pct: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    commission_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="reserved",
        comment="reserved | signed | closed | fallen",
    )
    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_sales_property", "tenant_id", "property_id"),
        Index("ix_sales_status", "tenant_id", "status"),
    )
