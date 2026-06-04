"""
Alembic env.py — entorno de migraciones.

Reconciliado en Phase 0a (V3 build plan):
- Usa el MISMO resolutor de URL que la app (``settings.resolved_database_url``),
  que reescribe ``postgresql://`` → ``postgresql+asyncpg://`` y normaliza ``ssl=``.
  Esto evita el crash de dialecto en Render (que inyecta ``postgresql://``).
- Importa el paquete ``app.db.models`` COMPLETO para que ``target_metadata`` contenga
  TODAS las tablas (antes solo importaba 5 de 13 → autogenerate las hubiera dropeado).
- ``include_object`` excluye tablas legacy gestionadas fuera del ORM (``bot_settings``,
  ``leads``, …) para que autogenerate no genere ``drop_table`` sobre ellas.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importar la base y TODOS los modelos.
# Importar el paquete registra cada modelo en Base.metadata (single source of truth
# tras la unificación de Base en Phase 0a). NO importar modelos sueltos: se omitirían
# tablas y autogenerate las trataría como "para dropear".
from app.db.base import Base
import app.db.models  # noqa: F401  (side-effect: registra todas las tablas)
from app.core.config import get_settings

# Config from alembic.ini
config = context.config

# === URL: un único resolutor, idéntico al de la app ===
settings = get_settings()
DATABASE_URL = settings.resolved_database_url
if not DATABASE_URL:
    # Fallback para Docker local
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/inmueblebot"

# Establecer la URL en la config de Alembic
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpretar el archivo de logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target para autogenerate
target_metadata = Base.metadata

# === Tablas gestionadas FUERA del ORM/Alembic ===
# Existen en prod (creadas por SQL crudo / startup migrations) pero no tienen modelo ORM,
# o son legacy. Excluirlas evita que autogenerate emita drop_table contra ellas.
UNMANAGED_TABLES = {
    "alembic_version",  # tabla de versiones de Alembic
    "bot_settings",     # key-value crudo (admin.py) — se migra a tenant_settings en Phase 1
    "leads",            # modelo legacy eliminado en Phase 0a (entidad viva = users)
}


def include_object(object_, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    """Excluir tablas no gestionadas del autogenerate."""
    if type_ == "table" and name in UNMANAGED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Ejecutar migraciones en modo offline."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )

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
