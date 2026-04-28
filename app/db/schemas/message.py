"""
Schemas de Mensaje (Pydantic).
Valida y serializa datos de mensajes.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class MessageBase(BaseModel):
    """Schema base para mensaje."""
    role: str = Field(..., description="Rol: user, assistant, system")
    content: str = Field(..., description="Contenido del mensaje")


class MessageCreate(MessageBase):
    """Schema para crear mensaje."""
    conversation_id: UUID
    media_url: Optional[str] = Field(None, max_length=500)


class MessageResponse(MessageBase):
    """Schema para respuesta de mensaje."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    conversation_id: UUID
    media_url: Optional[str]
    timestamp: datetime