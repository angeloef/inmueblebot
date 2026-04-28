from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum, Float
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class PropertyType(str, enum.Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    LAND = "land"
    COMMERCIAL = "commercial"
    OFFICE = "office"


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, index=True)
    name = Column(String(200))
    email = Column(String(200))
    status = Column(Enum(LeadStatus), default=LeadStatus.NEW)
    source = Column(String(50))
    notes = Column(Text)
    language = Column(String(2), default="es")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="lead")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)
    title = Column(String(300))
    description = Column(Text)
    property_type = Column(Enum(PropertyType))
    address = Column(String(500))
    city = Column(String(100))
    price = Column(Float)
    bedrooms = Column(Integer)
    bathrooms = Column(Integer)
    area = Column(Float)
    images = Column(Text)
    featured = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    appointments = relationship("Appointment", back_populates="property")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    property_id = Column(Integer, ForeignKey("properties.id"))
    scheduled_at = Column(DateTime)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.PENDING)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead = relationship("Lead", back_populates="appointments")
    property_rel = relationship("Property", back_populates="appointments")