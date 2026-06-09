from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Subscription(Base):
    """Estado de suscripción MercadoPago por tenant. Global, NO tenant-scoped por RLS."""
    __tablename__ = "subscriptions"

    id: Mapped[uuid4] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[uuid4] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(40), default="mercadopago", server_default="mercadopago", nullable=False,
    )
    mp_preapproval_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, unique=True,
    )
    mp_payer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="trial", server_default="trial", nullable=False,
        comment="trial | active | paused | cancelled | past_due",
    )
    plan: Mapped[str | None] = mapped_column(String(40), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), default="ARS", server_default="ARS", nullable=False,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<Subscription(tenant_id={self.tenant_id}, status={self.status})>"
