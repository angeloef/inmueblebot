"""
Modelo de Propiedad.
Representa inmobiliarias disponibles (venta/alquiler).
"""
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy import String, Integer, Float, DateTime, Index, CheckConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Property(Base):
    """
    Representa una propiedad inmobiliaria en venta o alquiler.
    """
    __tablename__ = "properties"

    # Integer primary key (seeded IDs from JSON data)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, comment="Primary key (seeded integer)")

    # Original seed ID (integer) for compatibility
    original_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, comment="Original seed ID (integer)")

    # ID externo (de sistema externo como API de imobiliarias)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        comment="ID de sistema externo"
    )

    # Título de la propiedad
    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        comment="Título de la propiedad"
    )

    # Descripción detallada
    description: Mapped[str] = mapped_column(
        String(5000),
        nullable=True,
        comment="Descripción de la propiedad"
    )

    # Precio en centavos/unidades enteras (evitar floating point)
    price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Precio en USD (entero)"
    )

    # Moneda
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        server_default="USD",
        comment="Moneda del precio"
    )

    # Tipo de operación: 'venta' o 'alquiler'
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tipo de operación: venta o alquiler"
    )

    # Ubicación/dirección
    location: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Dirección de la propiedad"
    )

    # Coordenadas geográficas (opcional)
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

    # Número de habitaciones
    bedrooms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Cantidad de dormitorios"
    )

    # Número de baños
    bathrooms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Cantidad de baños"
    )

    # Área en metros cuadrados
    area_m2: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Área en metros cuadrados"
    )

    # Imágenes (base64 data URIs or S3 URLs)
    images: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Lista de imágenes (data URIs base64 o URLs S3)"
    )

    # Estado de la propiedad
    status: Mapped[str] = mapped_column(
        String(20),
        default="available",
        server_default="available",
        comment="Estado: available, reserved, sold, rented"
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
    
    # Citas asociadas a esta propiedad
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="property_rel",
        cascade="all, delete-orphan"
    )

    # Índices y constraints
    __table_args__ = (
        # Validar que type sea 'venta' o 'alquiler'
        CheckConstraint(
            "type IN ('venta', 'alquiler')",
            name="ck_property_type"
        ),
        # Validar status
        CheckConstraint(
            "status IN ('available', 'reserved', 'sold', 'rented')",
            name="ck_property_status"
        ),
        # Índice para búsqueda por ubicación
        Index("ix_properties_location", "location"),
        # Índice para filtros de precio
        Index("ix_properties_price", "price"),
        # Índice para filtros combinados
        Index("ix_properties_type_status", "type", "status"),
    )

    def __repr__(self) -> str:
        return f"<Property(id={self.id}, title={self.title}, price={self.price})>"
