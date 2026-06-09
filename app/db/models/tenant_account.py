from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantAccount(Base):
    """Login de la inmobiliaria (email/password). Global, NO tenant-scoped por RLS."""
    __tablename__ = "tenant_accounts"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="FK al tenant (inmobiliaria)",
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), default="owner", server_default="owner", nullable=False,
        comment="owner | admin | superadmin",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Contador para invalidar tokens de email de un solo uso (reset/verify). Cada reset de
    # password lo incrementa, lo que invalida cualquier token de reset emitido antes (F-03).
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<TenantAccount(email={self.email}, tenant_id={self.tenant_id})>"
