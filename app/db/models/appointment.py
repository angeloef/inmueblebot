"""
Modelo de Cita/Appointment.
Representa una cita programada para visitar una propiedad.
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Appointment(Base):
    """
    Representa una cita programada para visitar una propiedad.
    """
    __tablename__ = "appointments"

    # UUID como primary key
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Primary key UUID"
    )

    # Agency (inmobiliaria) that owns this appointment. Nullable during Phase 1 backfill.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        comment="FK al tenant (inmobiliaria)"
    )

    # FK al usuario
    user_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK al usuario"
    )

    # FK a la propiedad (using Integer to match Property.id)
    property_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK a la propiedad"
    )

    # Fecha y hora de inicio (con timezone)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Fecha y hora de inicio de la cita"
    )

    # Fecha y hora de fin (con timezone)
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Fecha y hora de fin de la cita"
    )

    # Tipo de cita
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tipo: visit, signing, meeting"
    )

    # Estado de la cita
    status: Mapped[str] = mapped_column(
        String(20),
        default="confirmed",
        server_default="confirmed",
        comment="Estado: confirmed, cancelled, completed, no_show"
    )

    # ID del evento en calendario externo (Google Calendar, etc.)
    calendar_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ID de evento en calendario externo"
    )

    # Notas adicionales
    notes: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        comment="Notas adicionales de la cita"
    )

    # Agente atribuido (C5) — FK a tenant_members. Columna creada vía
    # ensure_operations_schema (ALTER IF NOT EXISTS).
    agent_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_members.id", ondelete="SET NULL"),
        nullable=True,
        comment="Agente (tenant_members) atribuido a la visita"
    )

    # Marca de cuándo se envió/encoló el recordatorio de visita (24h antes) — idempotencia
    # del job visit_reminder. NULL = pendiente de recordar.
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Cuándo se envió/encoló el recordatorio de visita 24h (idempotencia del job)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Fecha de creación"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment="Última actualización"
    )

    # =========================================================================
    # RELACIONES
    # =========================================================================
    
    # Usuario asociado
    user: Mapped["User"] = relationship(
        "User",
        back_populates="appointments"
    )

    # Propiedad asociada
    property_rel: Mapped["Property"] = relationship(
        "Property",
        back_populates="appointments"
    )

    # Índices y constraints
    __table_args__ = (
        CheckConstraint(
            "type IN ('visit', 'signing', 'meeting')",
            name="ck_appointment_type"
        ),
        CheckConstraint(
            "status IN ('confirmed', 'cancelled', 'completed', 'no_show')",
            name="ck_appointment_status"
        ),
        Index("ix_appointments_user_id", "user_id"),
        Index("ix_appointments_property_id", "property_id"),
        Index("ix_appointments_start_time", "start_time"),
        Index("ix_appointments_status", "status"),
        Index("ix_appointments_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Appointment(id={self.id}, user_id={self.user_id}, property_id={self.property_id})>"