"""
InmuebleBot - Asistente de bienes raíces por WhatsApp
Main application entry point / Punto de entrada de la aplicación
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

# Configurar logging con loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="INFO",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager para startup/shutdown de la aplicación.
    Maneja la inicialización y limpieza de recursos.
    """
    # Startup: inicializar conexiones, cargar configuración, etc.
    logger.info("🚀 Iniciando InmuebleBot...")
    
    # Check database tables on startup
    try:
        from sqlalchemy import text
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result.fetchall()]
            logger.info(f"[Startup] Found tables: {tables}")
            
            if "users" not in tables:
                logger.warning("[Startup] ⚠️ 'users' table not found! Creating tables...")
                try:
                    from app.db.create_tables import create_tables
                    await create_tables()
                    logger.info("[Startup] ✅ Tables created automatically")
                except Exception as create_error:
                    logger.warning(f"[Startup] Could not create tables: {create_error}")
            else:
                logger.info("[Startup] ✅ Database tables verified")
    except Exception as e:
        logger.warning(f"[Startup] Could not verify tables: {e}")
    
    # Check Redis connection on startup (with retry for Docker timing)
    try:
        import asyncio
        import redis.asyncio as redis
        
        redis_url = "redis://redis:6379/0"
        r = None
        
        for attempt in range(3):
            try:
                if r is None:
                    r = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
                await r.ping()
                await r.aclose()
                logger.info("[Startup] ✅ Redis: OK (connected to redis://redis:6379/0)")
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                    r = None
                else:
                    logger.warning(f"[Startup] ⚠️ Redis: UNAVAILABLE - running with limited memory ({e})")
    except Exception as e:
        logger.warning(f"[Startup] ⚠️ Redis: UNAVAILABLE - running with limited memory")
    
    logger.info("✅ InmuebleBot iniciado correctamente")
    
    yield  # La aplicación corre aquí
    
    # Shutdown: limpiar recursos
    logger.info("🛑 Cerrando InmuebleBot...")
    
    # TODO: Cerrar conexiones de base de datos
    # TODO: Cerrar conexión Redis
    # TODO: Guardar estado si es necesario
    
    logger.info("✅ Cierre completado")


# Crear aplicación FastAPI
app = FastAPI(
    title="InmuebleBot",
    description="Asistente de bienes raíces por WhatsApp / WhatsApp AI Real Estate Assistant",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Serve local test images as static files on /static/imagenes
app.mount("/static/imagenes", StaticFiles(directory="imagenes"), name="imagenes")
# Middleware CORS - permitir solicitudes desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: En producción, especificar dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Endpoint raíz - información básica de la API"""
    return {
        "message": "InmuebleBot API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """
    Health check endpoint para monitoring y readiness probes.
    Retorna el estado de salud de la aplicación incluyendo Redis.
    """
    from app.core.memory import memory_manager
    
    redis_status = await memory_manager.check_health()
    
    return {
        "status": "healthy" if redis_status.get("status") != "degraded" else "degraded",
        "service": "inmueblebot",
        "redis": redis_status
    }


@app.get("/health/redis")
async def health_redis():
    """
    Health check específico para Redis.
    """
    from app.core.memory import memory_manager
    
    result = await memory_manager.check_health()
    return result


# Importar y registrar routers (descomentar cuando estén implementados)
# from app.api.routes import webhook, admin, internal
# app.include_router(webhook.router, prefix="/api")
# app.include_router(admin.router, prefix="/api")
# app.include_router(internal.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", reload=True)
