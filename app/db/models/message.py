"""
Modelo de Mensaje.
Representa un mensaje individual en una conversación.
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import String, Text, DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Message(Base):
    """
    Representa un mensaje individual en una conversación.
    Puede ser del usuario, del asistente (LLM), o sistema.
    """
    __tablename__ = "messages"

    # BigSerial para alto volumen de mensajes (auto-increment)
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Primary key (BigSerial auto-increment)"
    )

    # FK a la conversación
    conversation_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK a la conversación"
    )

    # Rol del mensaje
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Rol: user, assistant, system"
    )

    # Sender: who sent the message — user, bot, or admin
    sender: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default='user',
        comment="Sender: user, bot, admin"
    )

    # Metadata JSONB — stores tools_called, router, latency_ms, confidence for bot messages
    msg_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Metadata: tools_called, router, latency_ms, confidence"
    )

    # Contenido del mensaje
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Contenido del mensaje"
    )

    # URL de media (imagen, audio, etc.) si aplica
    media_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL de archivo multimedia"
    )

    # Timestamp del mensaje
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Timestamp del mensaje"
    )

    # =========================================================================
    # RELACIONES
    # =========================================================================
    
    # Conversación asociada
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages"
    )

    # Índices
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_timestamp", "timestamp"),
        Index("ix_messages_role", "role"),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role}, conversation_id={self.conversation_id})>"