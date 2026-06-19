from datetime import datetime
from uuid import UUID as PyUUID  # noqa: N811  (alias evita choque con el tipo de columna UUID)
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SalesInquiry(Base):
    """Consulta Enterprise enviada desde la app (plan 20).

    Global, NO tenant-scoped por RLS — solo super-admin la lee.
    tenant_id para atribución/filtrado.
    """

    __tablename__ = "sales_inquiries"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    property_count: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        server_default="open",
        nullable=False,
        comment="open | contacted | closed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_sales_inquiries_status_created_at", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SalesInquiry(id={self.id}, status={self.status})>"
