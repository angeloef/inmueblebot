"""
InmuebleBot - Asistente de bienes raíces por WhatsApp
Main application entry point
"""
import sys
import os
import json
from datetime import datetime, timezone
from loguru import logger

# ============================================================================
# LOGGING JSON - Configuración simple y robusta
# ============================================================================
def configure_json_logging():
    """Configura logging JSON structurado de forma simple."""
    logger.remove()
    
    # Filtrar según entorno
    env = os.environ.get("ENVIRONMENT", "production").lower()
    level = "DEBUG" if env == "development" else "INFO"
    
# Usar serialize=True para output JSON automático
    logger.add(
        sys.stdout,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function} - {message}",
        level=level,
        serialize=True,
        enqueue=True,  # Thread-safe
    )

# Configurar
configure_json_logging()
logger.info("InmuebleBot starting")

# ============================================================================
# IMPORTS
# ============================================================================
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routes.webhook import router as webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    from sqlalchemy import text
    from app.db.session import async_session_factory
    
    logger.info("Starting up")
    
    try:
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result.fetchall()]
            logger.info("DB tables: {}", tables)
    except Exception as e:
        logger.warning("DB check failed: {}", e)
    
    yield
    logger.info("Shutting down")


# ============================================================================
# FASTAPI
# ============================================================================
app = FastAPI(
    title="InmuebleBot",
    description="Asistente inmobiliario por WhatsApp",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Static files
app.mount("/static/imagenes", StaticFiles(directory="imagenes"), name="imagenes")

# CORS - solo tu dominio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://inmueblebot-api.onrender.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
def root():
    return {"message": "InmuebleBot API", "version": "0.1.0", "docs": "/docs"}


@app.get("/health")
async def health():
    from app.core.memory import memory_manager
    redis_status = await memory_manager.check_health()
    return {"status": "healthy", "redis": redis_status.get("status")}


# Routers
app.include_router(webhook_router, prefix="/webhook", tags=["whatsapp"])

logger.info("InmuebleBot ready")