"""
Modelo de Usuario (Lead/Cliente).
Representa un contacto de WhatsApp que interactúa con el bot.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, func
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

    # Agency (inmobiliaria) that owns this lead. Nullable during the Phase 1 backfill;
    # tightened to NOT NULL after every row is attributed to a tenant.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="FK al tenant (inmobiliaria) dueño del lead",
    )

    whatsapp_phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        unique=False,
        index=True,
        nullable=True,
        comment="Número de WhatsApp del usuario (opcional para usuarios BSUID-only)"
    )

    # Business-Scoped User ID (Meta identity migration) — stable identity that
    # replaces the phone once usernames roll out. Nullable + indexed (non-unique
    # to keep the startup migration safe against any legacy dupes; identity
    # resolution treats it as the primary key). See [[meta-bsuid-identity-migration]].
    bsuid: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
        index=True,
        comment="BSUID de Meta (identificador estable, formato CC.alphanumeric)"
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

    extra_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Metadata adicional: email, role, notes (admin-created leads)"
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