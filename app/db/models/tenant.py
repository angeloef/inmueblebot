"""Tenant + TenantSettings ORM (V3 Phase 1 — multi-tenancy foundation).

A ``Tenant`` is an **inmobiliaria** (the agency that uses InmuebleBot) — the SaaS sense,
not the property renter. One Meta app serves many inmobiliarias; the inbound webhook
resolves the tenant by ``phone_number_id`` (decision D2).

The schema is intentionally designed so future self-serve signup + billing (out of scope
for V3, decision D6) are not blocked: ``plan``/``status`` columns exist now, nullable.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Tenant(Base):
    """An inmobiliaria using InmuebleBot (the SaaS tenant)."""

    __tablename__ = "tenants"

    id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4,
        comment="Primary key UUID (tenant/inmobiliaria id)",
    )

    # Multi-sucursal (Enterprise): jerarquía de tenants. NULL = tenant raíz (org Enterprise
    # o inmobiliaria standalone Profesional). Si está seteado, este tenant es una SUCURSAL
    # cuyo "dueño/org" es parent_tenant_id. La org padre no tiene número Meta propio; cada
    # sucursal hija sí. RLS org-aware: el GUC=org ve/escribe filas de todas sus hijas.
    parent_tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=True, index=True,
        comment="FK al tenant padre (org Enterprise). NULL = tenant raíz/standalone.",
    )

    slug: Mapped[str] = mapped_column(
        String(60), unique=True, index=True, nullable=False,
        comment="Slug estable y legible (p.ej. 'obera') para URLs/admin",
    )
    display_name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="Nombre visible de la inmobiliaria",
    )
    company_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Razón social / nombre legal",
    )

    # Operational config (per-inmobiliaria)
    business_hours: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment="Horario de atención (texto es-AR)",
    )
    timezone: Mapped[str] = mapped_column(
        String(60), default="America/Argentina/Cordoba",
        server_default="America/Argentina/Cordoba", nullable=False,
        comment="Zona horaria IANA para slots/horarios",
    )
    zones: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Zonas/barrios que opera la inmobiliaria (jsonb)",
    )
    branding: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Branding (logo, colores, firma) (jsonb)",
    )

    # WhatsApp (Meta) routing — one Meta app, many numbers (D2).
    waba_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="WhatsApp Business Account id de Meta",
    )
    phone_number_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True,
        comment="Phone Number ID de Meta — clave de ruteo del webhook inbound",
    )
    wa_access_token: Mapped[str | None] = mapped_column(
        String, nullable=True,
        comment="Access token de Meta CIFRADO (Fernet). Nunca plaintext. Ver app/core/crypto.py",
    )

    # Billing-ready (D6) — nullable, not used by V3 itself.
    plan: Mapped[str | None] = mapped_column(
        String(40), nullable=True, comment="Plan de facturación (futuro). Nullable.",
    )
    status: Mapped[str | None] = mapped_column(
        String(20), default="active", server_default="active", nullable=True,
        comment="Estado del tenant: active | suspended | trial (futuro)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    settings: Mapped[list["TenantSettings"]] = relationship(
        "TenantSettings", back_populates="tenant", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tenant(slug={self.slug}, phone_number_id={self.phone_number_id})>"


class TenantSettings(Base):
    """Per-tenant key/value bot config (supersedes the global ``bot_settings`` table).

    Replaces the single global 5-min cache with a tenant-keyed one (see prompts.py).
    Holds ``active_router``, ``company_name`` overrides, ``business_hours``, prompt
    overrides, etc. A global fallback row (tenant = default) preserves V2 behavior.
    """

    __tablename__ = "tenant_settings"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, comment="FK al tenant (inmobiliaria)",
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False, comment="Clave de config")
    value: Mapped[str | None] = mapped_column(String, nullable=True, comment="Valor (texto)")

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="settings")

    __table_args__ = (
        Index("uq_tenant_settings_tenant_key", "tenant_id", "key", unique=True),
    )

    def __repr__(self) -> str:
        return f"<TenantSettings(tenant_id={self.tenant_id}, key={self.key})>"
