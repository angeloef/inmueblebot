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
    )

    def __repr__(self) -> str:
        return f"<Appointment(id={self.id}, user_id={self.user_id}, property_id={self.property_id})>"