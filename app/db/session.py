"""
Módulo de sesión de base de datos.
Proporciona una fábrica de sesiones async para SQLAlchemy.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings


def get_async_session_factory():
    """
    Crea una factory de sesiones async.
    """
    settings = get_settings()
    db_url = settings.resolved_database_url
    engine = create_async_engine(db_url, echo=False)
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async_session_factory = get_async_session_factory()