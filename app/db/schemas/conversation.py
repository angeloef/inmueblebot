"""
Schemas de Conversación (Pydantic).
Valida y serializa datos de conversaciones.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.schemas.message import MessageResponse


class ConversationBase(BaseModel):
    """Schema base para conversación."""
    session_id: str = Field(..., max_length=100)
    state: str = "idle"


class ConversationCreate(ConversationBase):
    """Schema para crear conversación."""
    user_id: UUID
    context: Optional[dict] = None


class ConversationUpdate(BaseModel):
    """Schema para actualizar conversación."""
    state: Optional[str] = None
    context: Optional[dict] = None


class ConversationResponse(ConversationBase):
    """Schema para respuesta de conversación."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    context: Optional[dict]
    created_at: datetime
    updated_at: Optional[datetime]


class ConversationWithMessages(ConversationResponse):
    """Conversación con sus mensajes."""
    messages: list["MessageResponse"] = []