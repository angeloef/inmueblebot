"""
Módulo de sesión de base de datos.
Proporciona una fábrica de sesiones async para SQLAlchemy.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.tenant_session import install_tenant_guc_listener


def get_async_session_factory():
    """
    Crea una factory de sesiones async.

    Pool config (Phase 1): ``pool_pre_ping`` recycles dead connections; ``pool_reset_on_return``
    rolls back on return so no transaction-local tenant GUC can leak to the next checkout.
    """
    settings = get_settings()
    db_url = settings.resolved_database_url
    engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
    )
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Install the tenant GUC listener once at import time so every session created from this
# factory (including ad-hoc ``async_session_factory()`` callsites) is tenant-scoped.
install_tenant_guc_listener()

async_session_factory = get_async_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async DB dependency para rutas /auth y futuras. Tenant GUC vía listener global."""
    async with async_session_factory() as session:
        yield session