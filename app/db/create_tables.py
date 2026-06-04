"""
DESHABILITADO en Phase 0a (V3 build plan).

Antes esto corría ``Base.metadata.create_all`` en cada arranque, lo que compite con la
tabla de versiones de Alembic y causa drift silencioso de esquema. Alembic es ahora la
ÚNICA autoridad de DDL: las tablas se crean/migran con ``alembic upgrade head`` en deploy
(release command de Render).

Se mantiene la firma ``create_tables(echo)`` como no-op para no romper callsites legacy
(p. ej. ``app.main.lifespan``), que ya están gateados por ``RUN_LEGACY_STARTUP_MIGRATION``.
"""
import asyncio

from loguru import logger


async def create_tables(echo: bool = False) -> None:
    """No-op. La creación de tablas la hace Alembic (`alembic upgrade head`)."""
    logger.info(
        "create_tables() es no-op (Phase 0a): Alembic es la única autoridad de DDL. "
        "Usá `alembic upgrade head`."
    )


if __name__ == "__main__":
    asyncio.run(create_tables())
