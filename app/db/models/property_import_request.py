"""Solicitud de importación asistida de propiedades (plan 15).

El cliente (inmobiliaria) sube archivos + nota; los devs los procesan en superadmin.
Tabla global (sin RLS), igual que error_reports. Los adjuntos se guardan en la tabla
hija ``property_import_files`` (base64, igual patrón que documents).
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

IMPORT_STATUSES = ("received", "in_progress", "completed", "cancelled")

ALLOWED_CONTENT_TYPES = (
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/plain",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_FILES_PER_REQUEST = 10


class PropertyImportRequest(Base):
    __tablename__ = "property_import_requests"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid4 | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    requester_email: Mapped[str] = mapped_column(String(255), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="received", server_default="received", index=True
    )
    item_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    files: Mapped[list["PropertyImportFile"]] = relationship(
        "PropertyImportFile", back_populates="import_request", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PropertyImportRequest(id={self.id}, tenant={self.tenant_id}, status={self.status})>"  # noqa: E501


class PropertyImportFile(Base):
    __tablename__ = "property_import_files"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    import_request_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("property_import_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data: Mapped[str] = mapped_column(Text, nullable=False, comment="Contenido base64")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    import_request: Mapped["PropertyImportRequest"] = relationship(
        "PropertyImportRequest", back_populates="files"
    )

    def __repr__(self) -> str:
        return f"<PropertyImportFile(id={self.id}, filename={self.filename})>"
