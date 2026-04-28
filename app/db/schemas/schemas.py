from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class LeadBase(BaseModel):
    phone: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    language: Optional[str] = None


class LeadResponse(LeadBase):
    id: int
    status: str
    source: Optional[str]
    notes: Optional[str]
    language: str
    created_at: datetime

    class Config:
        from_attributes = True


class PropertyBase(BaseModel):
    title: str
    description: Optional[str] = None
    property_type: str
    address: str
    city: str
    price: float
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area: Optional[float] = None


class PropertyCreate(PropertyBase):
    images: Optional[list[str]] = None


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    featured: Optional[bool] = None
    active: Optional[bool] = None


class PropertyResponse(PropertyBase):
    id: int
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    area: Optional[float]
    images: Optional[list[str]]
    featured: bool
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AppointmentBase(BaseModel):
    lead_id: int
    property_id: int
    scheduled_at: datetime
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AppointmentResponse(AppointmentBase):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True