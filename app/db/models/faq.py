"""
Modelo de FAQ (Preguntas Frecuentes).
Representa una entrada de FAQ asociada a la inmobiliaria.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, Text, Boolean, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class FAQ(Base):
    """
    Entrada de preguntas frecuentes de la inmobiliaria.
    Cada entrada tiene una pregunta, respuesta, categoría opcional y tags para búsqueda.
    """
    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Primary key autoincremental"
    )

    # Agency (inmobiliaria) that owns this FAQ entry. Nullable during Phase 1 backfill.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        comment="FK al tenant (inmobiliaria)"
    )

    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Pregunta frecuente"
    )

    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Respuesta a la pregunta frecuente"
    )

    category: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Categoría (ej: financiación, horarios, proceso)"
    )

    tags: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Palabras clave para mejorar búsqueda"
    )

    order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Orden de visualización en el dashboard"
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Si está activa para ser usada por el bot"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Fecha de creación"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Fecha de última actualización"
    )

    __table_args__ = (
        Index("ix_faq_entries_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<FAQ id={self.id} question='{self.question[:50]}' category='{self.category}'>"
