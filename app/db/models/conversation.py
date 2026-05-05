"""
Modelo de Conversación.
Representa una sesión de chat entre usuario y el bot.
"""
from datetime import datetime
from typing import Optional, Dict, List
from uuid import uuid4
from sqlalchemy import String, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Conversation(Base):
    """
    Representa una sesión de conversación entre un usuario y el bot.
    Almacena el estado actual de la conversación para flow control.
    """
    __tablename__ = "conversations"

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

    # ID de sesión (para continuar conversaciones)
    session_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="ID de sesión para continuar conversaciones"
    )

    # Estado de la conversación (state machine)
    state: Mapped[str] = mapped_column(
        String(30),
        default="idle",
        server_default="idle",
        comment="Estado: idle, qualifying, searching, viewing, booking, closed"
    )

    # Contexto de la conversación (datos acumulados)
    context: Mapped[Optional[Dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Contexto de la conversación en JSON"
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
        back_populates="conversations"
    )

    # Mensajes de la conversación
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.timestamp"
    )

    # Índices
    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_session_id", "session_id"),
        Index("ix_conversations_state", "state"),
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, user_id={self.user_id}, state={self.state})>"