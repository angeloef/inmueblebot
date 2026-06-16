"""
Modelo de Log de Actividad unificado.

Registra eventos auditables sobre propiedades y clientes (vínculos, cambios de
estado, ediciones, reasignaciones) que alimentan el timeline "Visitas y actividad"
del dashboard. Los *datos estructurados* (contratos, autorizaciones) viven en sus
tablas; esta tabla solo guarda *eventos*.

La tabla se crea de forma idempotente en ``_run_startup_migration`` (admin.py),
siguiendo la convención del repo para tablas de admin (faq_entries, notifications,
bot_settings). Este modelo ORM existe para lecturas/escrituras tipadas.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityLog(Base):
    """Evento auditable sobre una propiedad o un cliente."""

    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Primary key UUID",
    )

    # Tenant (inmobiliaria / sucursal) dueño del evento. Nullable durante backfill,
    # igual que appointments.tenant_id.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        comment="FK al tenant (inmobiliaria/sucursal)",
    )

    # 'property' | 'client'
    entity_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Tipo de entidad: property | client",
    )

    # ID de la entidad como texto (Property.id es int, User.id es uuid → str unifica).
    entity_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="ID de la entidad (texto: properties.id o users.id)",
    )

    # Acción: status_changed, property_edited, reassigned,
    # relation_linked | relation_changed | relation_unlinked
    action: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="Acción registrada",
    )

    # Actor legible. Sin identidad de agente por request hoy → 'dashboard'.
    actor: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        server_default="dashboard",
        comment="Actor legible (p. ej. 'dashboard')",
    )

    # Identidad de usuario-agente para evolución futura (hoy NULL).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="FK futura al usuario-agente que ejecutó la acción",
    )

    # Detalle del evento: before/after, relation, nombres legibles. Sin PII sensible
    # ni tokens — solo lo necesario para describir el evento en el timeline.
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Detalle del evento (before/after, relation, nombres)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Fecha de creación del evento",
    )

    __table_args__ = (
        Index(
            "ix_activity_log_entity",
            "tenant_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityLog(entity={self.entity_type}:{self.entity_id}, " f"action={self.action})>"
        )
