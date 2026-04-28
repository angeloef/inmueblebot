"""
Modelo de Usuario (Lead/Cliente).
Representa un contacto de WhatsApp que interactúa con el bot.
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
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

    # Número de WhatsApp único (sin código de país +)
    whatsapp_phone: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Número de WhatsApp del usuario"
    )

    # Nombre del usuario (opcional, se colecta durante conversación)
    name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Nombre del usuario"
    )

    # Idioma preferido del usuario (es/en)
    preferred_language: Mapped[str] = mapped_column(
        String(2),
        default="es",
        server_default="es",
        comment="Idioma preferido del usuario"
    )

    # Rango de presupuesto mínimo
    budget_min: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Presupuesto mínimo en USD"
    )

    # Rango de presupuesto máximo
    budget_max: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Presupuesto máximo en USD"
    )

    # Preferencias de ubicación (array de strings)
    location_preferences: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Lista de ubicaciones preferidas"
    )

    # Tipos de propiedad buscados
    property_type: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="Tipos de propiedad感兴趣: ['casa', 'departamento', 'terreno']"
    )

    # Puntuación del lead (0-100) para priorización
    lead_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        comment="Puntuación del lead (0-100)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Fecha de creación del registro"
    )

    last_interaction: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Última interacción del usuario"
    )

    # =========================================================================
    # RELACIONES
    # =========================================================================
    
    # Conversaciones del usuario
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Citas del usuario
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Índices para rendimiento
    __table_args__ = (
        Index("ix_users_lead_score", "lead_score"),  # Para ordenar leads por score
        Index("ix_users_last_interaction", "last_interaction"),  # Para filtrar activos
    )

    def __repr__(self) -> str:
        return f"<User(phone={self.whatsapp_phone}, name={self.name})>"