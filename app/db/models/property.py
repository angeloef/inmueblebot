"""
Modelo de Propiedad.
Representa inmobiliarias disponibles (venta/alquiler).
"""
from datetime import datetime
from typing import Optional, List, Dict
from uuid import uuid4
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Index, CheckConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Property(Base):
    """
    Representa una propiedad inmobiliaria en venta o alquiler.
    """
    __tablename__ = "properties"

    # Integer primary key (seeded IDs from JSON data)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="Primary key (seeded integer)")

    # Agency (inmobiliaria) that owns this listing. Nullable during Phase 1 backfill.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        comment="FK al tenant (inmobiliaria) dueño de la propiedad",
    )

    # Original seed ID (integer) for compatibility
    original_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, comment="Original seed ID (integer)")

    # ID externo (de sistema externo como API de imobiliarias)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        comment="ID de sistema externo"
    )

    # Titulo de la propiedad
    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        comment="Titulo de la propiedad"
    )

    # Descripcion detallada
    description: Mapped[str] = mapped_column(
        String(5000),
        nullable=True,
        comment="Descripcion de la propiedad"
    )

    # Precio en centavos/unidades enteras (evitar floating point)
    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Precio en USD/ARS (entero)"
    )

    # Moneda
    currency: Mapped[str] = mapped_column(
        String(3),
        default="ARS",
        server_default="ARS",
        comment="Moneda del precio"
    )

    # Tipo de operacion: venta o alquiler
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tipo de operacion: venta o alquiler"
    )

    # Ubicacion/direccion
    location: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Direccion de la propiedad"
    )

    # Coordenadas geograficas (opcional)
    lat: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Latitud"
    )

    lng: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Longitud"
    )

    # Numero de habitaciones
    bedrooms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Cantidad de dormitorios"
    )

    # Numero de banos
    bathrooms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Cantidad de banos"
    )

    # Area en metros cuadrados
    area_m2: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Area en metros cuadrados"
    )

    # Imagenes (base64 data URIs or S3 URLs)
    images: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Lista de imagenes (data URIs base64 o URLs S3)"
    )

    # Estado de la propiedad
    status: Mapped[str] = mapped_column(
        String(20),
        default="available",
        server_default="available",
        comment="Estado: available, reserved, sold, rented"
    )

    # Tipo fisico: casa, departamento, ph, terreno
    category: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Tipo fisico: casa, departamento, ph, terreno"
    )

    # Metadatos adicionales (features, amenities, etc.)
    extra_data: Mapped[Optional[Dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Metadatos adicionales en formato JSON"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Fecha de creacion"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment="Ultima actualizacion"
    )

    # =========================================================================
    # RELACIONES
    # =========================================================================

    # Citas asociadas a esta propiedad
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="property_rel",
        cascade="all, delete-orphan"
    )

    # Indices y constraints
    __table_args__ = (
        CheckConstraint(
            "type IN ('venta', 'alquiler')",
            name="ck_property_type"
        ),
        CheckConstraint(
            "status IN ('available', 'reserved', 'sold', 'rented')",
            name="ck_property_status"
        ),
        Index("ix_properties_location", "location"),
        Index("ix_properties_price", "price"),
        Index("ix_properties_type_status", "type", "status"),
        Index("ix_properties_category", "category"),
        Index("ix_properties_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Property(id={self.id}, title={self.title}, price={self.price})>"
