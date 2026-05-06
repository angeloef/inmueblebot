"""
InmuebleBot - Asistente de bienes raíces por WhatsApp
Main application entry point
"""
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from loguru import logger

# ============================================================================
# LOGGING JSON - Configuración simple y robusta
# ============================================================================
logger.remove()
env = os.environ.get("ENVIRONMENT", "production").lower()
level = "DEBUG" if env == "development" else "INFO"
logger.add(
    sys.stdout,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}",
    level=level,
    serialize=True,
    enqueue=True,
)

logger.info("InmuebleBot starting")

# ============================================================================
# IMPORTS
# ============================================================================
from app.core.config import get_settings
from app.api.routes.webhook import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    from sqlalchemy import text
    from app.db.session import async_session_factory

    logger.info("Starting up")

    # Auto-create tables if they don't exist
    try:
        from app.db.create_tables import create_tables
        await create_tables(echo=False)
        logger.info("DB tables ensured")
    except Exception as e:
        logger.warning("Table creation failed: {}", e)

    try:
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result.fetchall()]
            logger.info("DB tables: {}", tables)
    except Exception as e:
        logger.warning("DB check failed: {}", e)

    # Auto-seed properties if none exist
    try:
        from app.db.seed import seed_properties
        # Force re-seed on startup if in development or DEBUG environment
        force_seed = os.environ.get("ENVIRONMENT", "production").lower() == "development"
        await seed_properties(force=force_seed)
    except Exception as e:
        logger.warning("Seed failed: {}", e)

    yield
    # Graceful shutdown: close Redis connections before event loop closes
    logger.info("Shutting down")
    try:
        from app.core.memory import memory_manager
        from app.core.classifier import intent_classifier
        from app.core.state_machine import state_machine
        await memory_manager.close()
        await intent_classifier.close()
        await state_machine.close()
    except Exception as e:
        logger.warning("Redis shutdown error: {}", e)


# ============================================================================
# FASTAPI
# ============================================================================
app = FastAPI(
    title="InmuebleBot",
    description="Asistente inmobiliario por WhatsApp / WhatsApp AI Real Estate Assistant",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Static files
if os.path.isdir("imagenes"):
    app.mount("/static/imagenes", StaticFiles(directory="imagenes"), name="imagenes")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://inmueblebot-api.onrender.com",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8051",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "InmuebleBot API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    from app.core.memory import memory_manager
    redis_status = await memory_manager.check_health()
    return {
        "status": "healthy" if redis_status.get("status") != "degraded" else "degraded",
        "service": "inmueblebot",
        "redis": redis_status,
    }


@app.get("/health/redis")
async def health_redis():
    from app.core.memory import memory_manager
    result = await memory_manager.check_health()
    return result


# ── Routers ─────────────────────────────────────────────────────────────────

# WhatsApp webhook
app.include_router(webhook_router, prefix="/webhook", tags=["whatsapp"])

# Admin dashboard API
from app.api.routes.admin import router as admin_router
app.include_router(admin_router)
logger.info("Admin router registered")

# ── Dashboard SPA ───────────────────────────────────────────────────────────
# Build dashboard: cd dashboard && npm install && npm run build
# Render multi-stage Dockerfile builds it automatically
_DASHBOARD_DIST = Path(__file__).parent.parent / "dashboard" / "dist"

if _DASHBOARD_DIST.exists():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=str(_DASHBOARD_DIST / "assets")), name="dashboard-assets")

    @app.get("/dashboard/{full_path:path}", include_in_schema=False)
    async def serve_dashboard(full_path: str):
        return FileResponse(str(_DASHBOARD_DIST / "index.html"))

    @app.get("/dashboard", include_in_schema=False)
    async def serve_dashboard_root():
        return FileResponse(str(_DASHBOARD_DIST / "index.html"))

    logger.info("Dashboard SPA served from dashboard/dist")
else:
    logger.info("Dashboard dist not found — run 'cd dashboard && npm install && npm run build' to enable")

logger.info("InmuebleBot ready")
