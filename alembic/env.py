"""
Alembic env.py - Configuración del entorno de migraciones.
Carga DATABASE_URL desde variable de entorno.
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importar la base y modelos
from app.db.base import Base
from app.db.models import User, Property, Conversation, Message, Appointment

# Config from alembic.ini
config = context.config

# === CARGAR DATABASE_URL DESDE ENTORNO ===
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Fallback para Docker: usar db service
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/inmueblebot"
    print(f"[Alembic] Usando DATABASE_URL por defecto: {DATABASE_URL}")
else:
    print(f"[Alembic] DATABASE_URL configurada: {DATABASE_URL[:30]}...")

# Validar que tiene el dialecto correcto
if DATABASE_URL and "postgresql+asyncpg://" not in DATABASE_URL:
    print(f"[Alembic] WARNING: DATABASE_URL no tiene postgresql+asyncpg driver")
    print(f"[Alembic] URL: {DATABASE_URL}")

# Establecer la URL en la config de Alembic
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpretar el archivo de logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ejecutar migraciones en modo offline."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Ejecutar migraciones en modo async."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Ejecutar migraciones en modo online (async)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()