"""Site brief — the intake the inmobiliaria fills so the founder can build their public web.

One row per tenant (the agency). Phase A of the "Sitio web con catálogo" item: this captures
everything needed to build the site MANUALLY (no templates / no auto-gen yet). The form lives
in the dashboard ("Mi sitio web"); the founder reads the submitted brief and builds the web.

Sections are stored as JSONB so the intake form can evolve without a migration each time:
  - brand   : nombre comercial, logo, colores, tipografía, fotos local/equipo.
  - pitch   : descripción, historia, diferencial, público objetivo (texto personalizado).
  - contact : whatsapp, teléfono, email, dirección, horarios, redes, matrícula.
  - domain  : ¿tienen dominio?, cuál, ¿lo compramos nosotros?, estado DNS.
  - design  : preferencias de diseño (presets + texto libre): estilo, paleta, referencias, evitar.
  - catalog : operaciones a publicar, campos a mostrar/ocultar, CTA al WhatsApp del bot.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SiteBrief(Base):
    """Brief de la web pública de una inmobiliaria (un registro por tenant)."""

    __tablename__ = "tenant_site_briefs"

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4,
        comment="Primary key UUID",
    )
    # Agency (inmobiliaria). Unique: a tenant has at most one brief.
    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, comment="FK al tenant (inmobiliaria) — único por tenant",
    )

    # draft = en edición · submitted = enviado al founder · in_progress = armando · live = publicado
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft",
        comment="draft | submitted | in_progress | live",
    )

    # Secciones del brief (JSONB flexible — el form mapea 1:1).
    brand: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    pitch: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    contact: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    domain: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    design: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    catalog: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    __table_args__ = (
        Index("uq_site_briefs_tenant", "tenant_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<SiteBrief(tenant_id={self.tenant_id}, status={self.status})>"
