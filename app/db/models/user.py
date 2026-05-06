"""
Modelo de Usuario (Lead/Cliente).
Representa un contacto de WhatsApp que interactúa con el bot.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class User(Base):
    """
    Representa un usuario/lead que contacta al bot por WhatsApp.
    Almacena preferencias y metadata de calificación del lead.
    """
    __tablename__ = "users"

    # UUID como primary key usando uuid_generate_v4()
    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        comment="Primary key UUID"
    )

    whatsapp_phone: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
        comment="Número de WhatsApp del usuario"
    )

    name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Nombre del usuario"
    )

    preferred_language: Mapped[str] = mapped_column(
        String(10),
        default="es",
        comment="Idioma preferido (es/en)"
    )

    budget_min: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Presupuesto mínimo en USD"
    )

    budget_max: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Presupuesto máximo en USD"
    )

    location_preferences: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Lista de ubicaciones de interés"
    )

    property_type: Mapped[Optional[List[str]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Tipos de propiedad preferidos"
    )

    lead_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Puntuación de lead (0-100)"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    last_interaction: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(phone={self.whatsapp_phone}, name={self.name})>"