"""Database engine and session management (legacy ``cs_*`` path).

Reconciliado en Phase 0a:
- Usa ``settings.resolved_database_url`` (mismo resolutor que app + alembic), no la URL
  cruda (que rompe el dialecto async en Render).
- ``create_tables`` quedó DESHABILITADO: Alembic es la única autoridad de DDL en deploy.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.tenant_session import install_tenant_guc_listener

settings = get_settings()

# Tenant GUC + RLS (Phase 1): pool_reset_on_return rolls back on checkin so the
# transaction-local tenant setting cannot leak across pooled connections.
install_tenant_guc_listener()

engine = create_async_engine(
    settings.resolved_database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async database session."""
    async with async_session() as session:
        yield session


async def ping_db() -> bool:
    """Check database connectivity with a simple query."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def create_tables() -> None:
    """DISABLED (Phase 0a).

    DDL is owned exclusively by Alembic (`alembic upgrade head` on deploy). Creating
    tables here would race the migration version table and cause silent schema drift.
    """
    raise RuntimeError(
        "create_tables() is disabled — Alembic is the single DDL authority. "
        "Run `alembic upgrade head` instead."
    )
