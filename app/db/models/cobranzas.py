"""
Modelos de Cobranzas (gestión de alquileres).

Define los contratos de alquiler, los cobros mensuales (cuotas), los gastos
asociados al contrato y los valores de índices económicos (IPC) usados para
calcular los aumentos.

Diseño scheduler-ready: el cálculo de aumentos/punitorios y la generación de
cuotas viven en `app/services/billing_service.py` como funciones puras e
idempotentes. Hoy se disparan manualmente desde el panel; en el futuro un
scheduler las llamará sin cambios en el core.
"""
from datetime import datetime, date
from typing import Optional, List
from uuid import uuid4
from sqlalchemy import (
    String, Integer, Float, Date, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Contract(Base):
    """Contrato de alquiler entre un propietario y un inquilino sobre una propiedad."""
    __tablename__ = "contracts"

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4,
        comment="Primary key UUID",
    )

    # FK a la propiedad (Integer para coincidir con Property.id)
    property_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("properties.id", ondelete="SET NULL"),
        nullable=True, comment="FK a la propiedad alquilada",
    )
    # Inquilino y propietario (FK a users.id, UUID)
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, comment="FK al inquilino (users)",
    )
    owner_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, comment="FK al propietario (users)",
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False, comment="Inicio del contrato")
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, comment="Fin del contrato")

    base_rent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="Alquiler base inicial (entero, en la moneda del contrato)",
    )
    currency: Mapped[str] = mapped_column(String(3), default="ARS", server_default="ARS")

    payment_due_day: Mapped[int] = mapped_column(
        Integer, default=10, server_default="10",
        comment="Día del mes de vencimiento del pago (1-31)",
    )
    grace_days: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Días de gracia antes de aplicar punitorios",
    )

    # Configuración de ajuste (aumentos)
    adjustment_index: Mapped[str] = mapped_column(
        String(20), default="IPC", server_default="IPC",
        comment="Índice de ajuste: IPC | fixed | none",
    )
    adjustment_frequency_months: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3",
        comment="Frecuencia de ajuste en meses (3, 4, 6, 12...)",
    )
    adjustment_fixed_pct: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
        comment="Porcentaje fijo por ajuste (solo si adjustment_index='fixed')",
    )

    # Punitorios y comisión
    punitorio_daily_pct: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0",
        comment="Porcentaje diario de punitorio sobre el saldo vencido",
    )
    commission_pct: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0",
        comment="Comisión de la inmobiliaria (% sobre lo cobrado) para liquidaciones",
    )

    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active",
        comment="Estado: active | ended | cancelled",
    )

    # Token para el portal público del inquilino (Fase 2) — se genera ahora.
    public_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True,
        comment="Token del portal público del inquilino (Fase 2)",
    )

    notes: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    # Relaciones (solo las de FK única, para evitar ambigüedad con tenant/owner)
    charges: Mapped[List["Charge"]] = relationship(
        "Charge", back_populates="contract", cascade="all, delete-orphan",
    )
    expenses: Mapped[List["ContractExpense"]] = relationship(
        "ContractExpense", back_populates="contract", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_contracts_status", "status"),
        Index("ix_contracts_property_id", "property_id"),
        Index("ix_contracts_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Contract(id={self.id}, property_id={self.property_id}, base_rent={self.base_rent})>"


class Charge(Base):
    """Cobro mensual (cuota) de un contrato de alquiler."""
    __tablename__ = "charges"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    contract_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False, comment="FK al contrato",
    )

    period: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Mes del cobro (primer día del mes)",
    )
    due_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="Fecha de vencimiento del cobro",
    )

    base_amount: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Monto del alquiler del período (editable mes a mes)",
    )
    adjustment_amount: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Porción del aumento vs. alquiler base (informativo)",
    )
    expenses_amount: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Gastos/servicios del período (snapshot al pagar)",
    )
    punitorio_amount: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Punitorios (snapshot al pagar; calculado al vuelo si está pendiente)",
    )
    total_amount: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
        comment="Total (base + gastos + punitorios) — snapshot al pagar",
    )
    amount_paid: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="Monto efectivamente cobrado",
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending",
        comment="Estado: pending | paid | partial | cancelled",
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="charges")

    __table_args__ = (
        UniqueConstraint("contract_id", "period", name="uq_charge_contract_period"),
        Index("ix_charges_contract_id", "contract_id"),
        Index("ix_charges_status", "status"),
        Index("ix_charges_period", "period"),
    )

    def __repr__(self) -> str:
        return f"<Charge(id={self.id}, period={self.period}, status={self.status})>"


class ContractExpense(Base):
    """Gasto o servicio asociado a un contrato (expensas, servicios, reparaciones...)."""
    __tablename__ = "contract_expenses"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    contract_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
    )
    charge_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charges.id", ondelete="SET NULL"), nullable=True,
        comment="Cobro al que se imputa (opcional)",
    )

    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
    amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    category: Mapped[str] = mapped_column(
        String(40), default="otro", server_default="otro",
        comment="servicio | expensas | reparacion | otro",
    )
    period: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="Mes al que aplica (si no es recurrente)",
    )
    recurring: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
        comment="Si aplica todos los meses del contrato",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    contract: Mapped["Contract"] = relationship("Contract", back_populates="expenses")

    __table_args__ = (
        Index("ix_contract_expenses_contract_id", "contract_id"),
    )

    def __repr__(self) -> str:
        return f"<ContractExpense(id={self.id}, amount={self.amount}, category={self.category})>"


class EconomicIndex(Base):
    """
    Valor de un índice económico (IPC) para un mes dado.

    Se carga manualmente hoy; un fetcher de INDEC podrá escribir en la misma
    tabla en el futuro (source='indec_api'). El coeficiente de ajuste se calcula
    como index_level[mes_ajuste] / index_level[mes_inicio].
    """
    __tablename__ = "economic_indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(20), default="IPC", server_default="IPC", comment="Código del índice (IPC)",
    )
    period: Mapped[date] = mapped_column(
        Date, nullable=False, comment="Mes del valor (primer día del mes)",
    )
    index_level: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Número índice (nivel general INDEC)",
    )
    monthly_pct: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Variación mensual % (opcional / informativo)",
    )
    source: Mapped[str] = mapped_column(
        String(20), default="manual", server_default="manual", comment="manual | indec_api",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("code", "period", name="uq_economic_index_code_period"),
        Index("ix_economic_indices_code", "code"),
    )

    def __repr__(self) -> str:
        return f"<EconomicIndex(code={self.code}, period={self.period}, level={self.index_level})>"
