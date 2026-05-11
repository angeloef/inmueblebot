"""
Genera las tablas de la base de datos.
Útil para desarrollo sin migraciones de Alembic.
"""
import asyncio
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.base import Base
from app.db.models import User, Property, Conversation, Message, Appointment, FAQ
from app.core.config import get_settings


async def create_tables(echo: bool = False):
    """Crea todas las tablas en la base de datos."""
    settings = get_settings()
    
    engine = create_async_engine(settings.DATABASE_URL, echo=echo)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    logger.info("Database tables created successfully")


if __name__ == "__main__":
    asyncio.run(create_tables())