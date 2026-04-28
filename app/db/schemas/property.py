"""
Schemas de Propiedad (Pydantic).
Valida y serializa datos de propiedades.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


# =============================================================================
# Schemas base
# =============================================================================


class PropertyBase(BaseModel):
    """Schema base para propiedad."""
    title: str = Field(..., max_length=300, description="Título de la propiedad")
    description: Optional[str] = Field(None, max_length=5000, description="Descripción")
    price: int = Field(..., ge=0, description="Precio en USD")
    currency: str = Field("USD", max_length=3, description="Moneda")
    type: str = Field(..., description="Tipo: venta o alquiler")
    location: str = Field(..., max_length=500, description="Dirección")
    lat: Optional[float] = None
    lng: Optional[float] = None


class PropertyCreate(PropertyBase):
    """Schema para crear propiedad."""
    external_id: Optional[str] = Field(None, max_length=100)
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    area_m2: Optional[int] = Field(None, ge=0)
    images: Optional[list[str]] = None
    extra_data: Optional[dict] = None


class PropertyUpdate(BaseModel):
    """Schema para actualizar propiedad."""
    title: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = Field(None, max_length=5000)
    price: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    type: Optional[str] = None
    location: Optional[str] = Field(None, max_length=500)
    lat: Optional[float] = None
    lng: Optional[float] = None
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    area_m2: Optional[int] = Field(None, ge=0)
    images: Optional[list[str]] = None
    status: Optional[str] = None
    extra_data: Optional[dict] = None


# =============================================================================
# Schemas de respuesta
# =============================================================================


class PropertyResponse(PropertyBase):
    """Schema para respuesta de propiedad."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    external_id: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    area_m2: Optional[int]
    images: Optional[list[str]]
    status: str
    extra_data: Optional[dict]
    created_at: datetime
    updated_at: Optional[datetime]


class PropertyListResponse(BaseModel):
    """Schema para lista de propiedades."""
    properties: list[PropertyResponse]
    total: int


# =============================================================================
# Schemas de búsqueda
# =============================================================================


class PropertySearchParams(BaseModel):
    """Parámetros de búsqueda de propiedades."""
    type: Optional[str] = None  # venta/alquiler
    location: Optional[str] = None
    budget_min: Optional[int] = Field(None, ge=0)
    budget_max: Optional[int] = Field(None, ge=0)
    bedrooms_min: Optional[int] = Field(None, ge=0)
    bathrooms_min: Optional[int] = Field(None, ge=0)
    area_min: Optional[int] = Field(None, ge=0)
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)