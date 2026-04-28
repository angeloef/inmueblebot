"""
Schemas de Cita (Pydantic).
Valida y serializa datos de citas/appointments.
"""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class AppointmentBase(BaseModel):
    """Schema base para cita."""
    type: str = Field(..., description="Tipo: visit, signing, meeting")
    status: str = "confirmed"


class AppointmentCreate(AppointmentBase):
    """Schema para crear cita."""
    user_id: UUID
    property_id: UUID
    start_time: datetime
    end_time: datetime
    notes: Optional[str] = Field(None, max_length=1000)


class AppointmentUpdate(BaseModel):
    """Schema para actualizar cita."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    type: Optional[str] = None
    status: Optional[str] = None
    calendar_event_id: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)


class AppointmentResponse(AppointmentBase):
    """Schema para respuesta de cita."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    property_id: UUID
    start_time: datetime
    end_time: datetime
    calendar_event_id: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class AppointmentListResponse(BaseModel):
    """Schema para lista de citas."""
    appointments: list[AppointmentResponse]
    total: int