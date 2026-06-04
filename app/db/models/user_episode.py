"""UserEpisode ORM — durable session records for cross-session recall."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserEpisode(Base):
    """A summary of a user session, stored durably in PostgreSQL."""

    __tablename__ = "user_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Agency (inmobiliaria) that owns this episode. Nullable during Phase 1 backfill.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="FK al tenant (inmobiliaria)",
    )
    phone: Mapped[str] = mapped_column(String(30), index=True)
    bsuid: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), unique=True)

    # Session summary
    summary: Mapped[str] = mapped_column(Text, default="")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    last_tool_called: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Search context
    search_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    properties_viewed: Mapped[list[int]] = mapped_column(JSON, default=list)
    intent_outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # TIMESTAMPTZ (Phase 1) — required before Phase 4 tenant-local business-hours math.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class ZoneStat(Base):
    """Aggregated zone statistics from search patterns (per inmobiliaria)."""

    __tablename__ = "zone_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Agency (inmobiliaria). Nullable during Phase 1 backfill. Note: zone_name is no longer
    # globally unique once scoped — uniqueness becomes (tenant_id, zone_name); see migration.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="FK al tenant (inmobiliaria)",
    )
    zone_name: Mapped[str] = mapped_column(String(50), index=True)
    search_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_price_alquiler: Mapped[float] = mapped_column(Integer, default=0)
    avg_price_venta: Mapped[float] = mapped_column(Integer, default=0)
    property_count: Mapped[int] = mapped_column(Integer, default=0)
    amenities: Mapped[list[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("uq_zone_stats_tenant_zone", "tenant_id", "zone_name", unique=True),
    )


class SearchFailure(Base):
    """Dead-end search criteria combos — avoid suggesting (per inmobiliaria)."""

    __tablename__ = "search_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Agency (inmobiliaria). Nullable during Phase 1 backfill.
    tenant_id: Mapped[Optional[uuid4]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="FK al tenant (inmobiliaria)",
    )
    operation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    zone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Integer, nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, default=1)
    last_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
