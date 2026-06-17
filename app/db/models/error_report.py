from datetime import datetime
from uuid import UUID as PyUUID  # noqa: N811  (alias evita choque con el tipo de columna UUID)
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ErrorReport(Base):
    """Reporte de error enviado desde la app por un usuario de una inmobiliaria.

    Global, NO tenant-scoped por RLS (igual que ``subscriptions``): el triage lo hacen
    los super-admin cross-tenant. ``tenant_id`` queda para filtrar/atribuir el reporte.
    """

    __tablename__ = "error_reports"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reporter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    severity: Mapped[str] = mapped_column(
        String(20),
        default="med",
        server_default="med",
        nullable=False,
        comment="low | med | high",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        server_default="open",
        nullable=False,
        comment="open | in_progress | resolved | wont_fix",
    )
    triage_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    __table_args__ = (Index("ix_error_reports_status_created_at", "status", "created_at"),)

    def __repr__(self) -> str:
        return f"<ErrorReport(id={self.id}, status={self.status}, severity={self.severity})>"
