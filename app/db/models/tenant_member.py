from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MEMBER_PENDING = "pending"
MEMBER_ACCEPTED = "accepted"
MEMBER_REVOKED = "revoked"


class TenantMember(Base):
    __tablename__ = "tenant_members"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default=MEMBER_PENDING, server_default="pending", nullable=False,
    )
    invite_token: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    account_id: Mapped[uuid4 | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<TenantMember(email={self.email}, tenant_id={self.tenant_id}, status={self.status})>"
