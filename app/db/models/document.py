"""Documento adjunto a un cliente y/o contrato (plan Enterprise).

DNI, recibos de sueldo, contratos firmados, garantías. El archivo se guarda como base64
en la propia base (igual que las fotos de propiedades), con límite de tamaño en la API.
Tenant-scoped (RLS org-aware, migración 0014): cada sucursal ve los suyos; el dueño en
consolidado ve los de todas sus sucursales.
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Categorías predefinidas (validadas en la API).
DOCUMENT_CATEGORIES = ("dni", "recibo", "contrato_firmado", "garantia", "otros")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="FK al tenant (inmobiliaria/sucursal)",
    )

    # Al menos uno de los dos debe estar seteado (validado en la API).
    client_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="Cliente al que pertenece (users.id)",
    )
    contract_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="Contrato al que pertenece (contracts.id)",
    )

    category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="dni | recibo | contrato_firmado | garantia | otros",
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="MIME (application/pdf, image/jpeg, …)",
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="Tamaño del archivo decodificado",
    )
    # base64 del archivo (sin el prefijo data URI). Igual patrón que las fotos.
    data: Mapped[str] = mapped_column(Text, nullable=False, comment="Contenido base64")
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Email de quien subió el documento",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, category={self.category}, filename={self.filename})>"
