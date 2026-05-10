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

    # ── Column-type migration: ensure varchar[] (not JSONB) for array prefs ──
    try:
        async with async_session_factory() as session:
            for col in ("property_type", "location_preferences"):
                result = await session.execute(text(
                    f"SELECT data_type FROM information_schema.columns "
                    f"WHERE table_name='users' AND column_name='{col}'"
                ))
                row = result.fetchone()
                if row and row[0] == "jsonb":
                    logger.warning(
                        f"[Migration] users.{col} is JSONB — migrating to varchar[]"
                    )
                    await session.execute(text(
                        f"ALTER TABLE users ALTER COLUMN {col} "
                        f"TYPE character varying[] "
                        f"USING ARRAY(SELECT jsonb_array_elements_text({col}))::varchar[]"
                    ))
                    await session.commit()
                    logger.info(f"[Migration] users.{col} migrated to varchar[] ✓")
    except Exception as e:
        logger.warning(f"[Migration] varchar[] column check failed (non-fatal): {e}")

    # Auto-seed properties only if the table is empty (never force on startup)
    try:
        from app.db.seed import seed_properties
        await seed_properties(force=False)
    except Exception as e:
        logger.warning("Seed failed: {}", e)

    # Pre-warm Calendar OAuth at startup (avoids 2s cold start on first appointment)
    try:
        from app.services.calendar_service import calendar_service
        _ = calendar_service.service  # triggers OAuth init if credentials exist
        logger.info("[Calendar] Service pre-warmed at startup")
    except Exception:
        pass  # Calendar not configured, that's fine

    # Auto-reset context for test phone so every deploy starts fresh
    try:
        import os
        reset_phone = os.environ.get("RESET_PHONE_ON_STARTUP") or "5493754455340"
        from app.core.memory import memory_manager
        await memory_manager.reset_user_context(reset_phone)
        logger.info(f"[Startup] Context auto-reset for test phone {reset_phone}")
    except Exception as e:
        logger.warning(f"[Startup] Context reset skipped (non-fatal): {e}")

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


@app.get("/media/property/{property_id}/{image_index}", include_in_schema=False)
async def serve_property_image(property_id: str, image_index: int):
    """
    Serve a property image as binary.
    Images stored as data:image/...;base64,... in the DB are decoded on-the-fly
    so WhatsApp (which only accepts public HTTPS URLs) can fetch them.
    """
    import re
    import base64
    from fastapi.responses import Response, RedirectResponse

    # Minimal 1x1 grey JPEG placeholder for fallback (WhatsApp can't handle 404 on media URLs)
    _PLACEHOLDER_JPEG = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f'
        b'\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c\x20\x24\x2e\x27\x20\x22\x2c\x23\x1c\x1c\x28\x37\x29\x2c\x30\x31\x34\x34'
        b'\x1f\x27\x39\x3d\x38\x32\x3c\x2e\x33\x34\x32\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xd9'
    )
    from app.db.session import async_session_factory
    from app.db.repository import BaseRepository
    from app.db.models import Property

    try:
        async with async_session_factory() as session:
            repo = BaseRepository(Property, session)

            prop = None
            # Try UUID
            try:
                from uuid import UUID
                prop = await repo.get(UUID(property_id))
            except Exception:
                pass
            # Try integer ID
            if not prop:
                try:
                    from sqlalchemy import select
                    result = await session.execute(
                        select(Property).where(Property.id == int(property_id))
                    )
                    prop = result.scalar_one_or_none()
                except Exception:
                    pass

            if not prop or not getattr(prop, "images", None):
                return Response(status_code=404)

            images = prop.images
            if image_index < 0 or image_index >= len(images):
                return Response(status_code=404)

            image_data = images[image_index]

            # Force convert WebP to JPEG (WhatsApp doesn't accept WebP)
            # Normalize: if image is raw base64 (no data: prefix), try to detect mime type from magic bytes
            if isinstance(image_data, str):
                if not image_data.startswith("data:") and not image_data.startswith("http"):
                    # Detect mime type from base64-decoded header magic bytes
                    try:
                        raw_bytes = base64.b64decode(image_data[:100])
                        if raw_bytes[:2] == b'\xff\xd8':
                            mime = "image/jpeg"
                        elif raw_bytes[:4] == b'\x89PNG':
                            mime = "image/png"
                        elif raw_bytes[:4] == b'RIFF' and raw_bytes[8:12] == b'WEBP':
                            mime = "image/webp"
                        elif raw_bytes[:2] == b'G\x49' or raw_bytes[:2] == b'G\x38':
                            mime = "image/gif"
                        elif raw_bytes[:4] == b'\x00\x00\x01\x00':
                            mime = "image/x-icon"
                        else:
                            mime = "image/jpeg"
                    except Exception:
                        mime = "image/jpeg"
                    image_data = f"data:{mime};base64,{image_data}"

            # data:image/jpeg;base64,<payload>
            if image_data.startswith("data:"):
                match = re.match(r"data:([^;]+);base64,(.+)$", image_data, re.DOTALL)
                if not match:
                    logger.warning(f"[Media] Bad data URI for property {property_id} image {image_index}")
                    # Fallback: return a minimal 1x1 JPEG placeholder so WhatsApp doesn't hang
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
                mime_type = match.group(1).strip()
                b64_payload = match.group(2).strip()
                try:
                    binary = base64.b64decode(b64_payload)
                except Exception:
                    logger.warning(f"[Media] Base64 decode failed for property {property_id} image {image_index}")
                    # Fallback: return a placeholder so WhatsApp doesn't hang
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
                # If the image is WebP, convert to JPEG (WhatsApp restriction)
                if mime_type in ("image/webp", "image/webp;"):
                    try:
                        from PIL import Image
                        import io
                        webp_img = Image.open(io.BytesIO(binary))
                        # Convert RGBA to RGB for JPEG compatibility
                        if webp_img.mode == "RGBA":
                            webp_img = webp_img.convert("RGB")
                        jpeg_buf = io.BytesIO()
                        webp_img.save(jpeg_buf, format="JPEG", quality=85)
                        binary = jpeg_buf.getvalue()
                        mime_type = "image/jpeg"
                    except Exception as e:
                        logger.warning(f"[Media] WebP→JPEG conversion failed for property {property_id}: {e}")
                        # Fallback: serve it anyway, WhatsApp may accept or not
                # Validate min image size (at least 100 bytes of valid image data)
                if len(binary) < 100:
                    logger.warning(f"[Media] Image too small ({len(binary)} bytes) for property {property_id}")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
                return Response(content=binary, media_type=mime_type)

            # Regular URL — redirect WhatsApp to it
            if image_data.startswith("http"):
                return RedirectResponse(url=image_data)

            # Unknown format
            logger.warning(f"[Media] Unknown image format for property {property_id} image {image_index}")
            return Response(status_code=404)

    except Exception as e:
        logger.error(f"[Media] Error serving property {property_id} image {image_index}: {e}")
        return Response(status_code=500)


# ── Global Exception Handler ────────────────────────────────────────────────
from fastapi.responses import JSONResponse
from starlette.requests import Request


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions, log them, and return a friendly response."""
    logger.opt(exception=True).error(
        "Unhandled exception on {} {}: {}",
        request.method,
        request.url.path,
        repr(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "message": "Ocurrió un error interno. Por favor intentá de nuevo.",
        },
    )


# ── Routers ─────────────────────────────────────────────────────────────────

# WhatsApp webhook
app.include_router(webhook_router, prefix="/webhook", tags=["whatsapp"])

# Admin dashboard API
from app.api.routes.admin import router as admin_router
app.include_router(admin_router)

# Also expose admin routes at /api/admin/* so the compiled dashboard bundle works
# on Render (no Nginx proxy). In Docker, Nginx strips /api/ before forwarding to
# FastAPI; on Render the Python app serves the dashboard directly, so /api/ must
# be registered here too.
from fastapi import APIRouter as _APIRouter
_api_compat = _APIRouter(prefix="/api")
_api_compat.include_router(admin_router)
app.include_router(_api_compat)

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
