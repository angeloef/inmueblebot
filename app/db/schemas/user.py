"""
Schemas de Usuario (Pydantic).
Valida y serializa datos de usuarios/leads.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


# =============================================================================
# Schemas base
# =============================================================================


class UserBase(BaseModel):
    """Schema base para usuario."""
    whatsapp_phone: Optional[str] = Field(None, max_length=20, description="Número de WhatsApp (opcional, BSUID-only users)")
    name: Optional[str] = Field(None, max_length=200, description="Nombre del usuario")
    preferred_language: str = Field("es", description="Idioma preferido")
    bsuid: Optional[str] = Field(None, description="BSUID de Meta (identificador estable)")


class UserCreate(UserBase):
    """Schema para crear un nuevo usuario."""
    budget_min: Optional[int] = Field(None, ge=0, description="Presupuesto mínimo")
    budget_max: Optional[int] = Field(None, ge=0, description="Presupuesto máximo")
    location_preferences: Optional[list[str]] = Field(None, description="Ubicaciones preferidas")
    property_type: Optional[list[str]] = Field(None, description="Tipos de propiedad")


class UserUpdate(BaseModel):
    """Schema para actualizar usuario."""
    name: Optional[str] = Field(None, max_length=200)
    preferred_language: Optional[str] = Field(None, max_length=2)
    budget_min: Optional[int] = Field(None, ge=0)
    budget_max: Optional[int] = Field(None, ge=0)
    location_preferences: Optional[list[str]] = None
    property_type: Optional[list[str]] = None
    lead_score: Optional[int] = Field(None, ge=0, le=100)
    last_interaction: Optional[datetime] = None


# =============================================================================
# Schemas de respuesta
# =============================================================================


class UserResponse(UserBase):
    """Schema para respuesta de usuario."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    budget_min: Optional[int]
    budget_max: Optional[int]
    location_preferences: Optional[list[str]]
    property_type: Optional[list[str]]
    lead_score: int
    created_at: datetime
    last_interaction: Optional[datetime]


class UserListResponse(BaseModel):
    """Schema para lista de usuarios."""
    users: list[UserResponse]
    total: int