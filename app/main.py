from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# ── App ──────────────────────────────────────────────────────────

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
                if row and row[0] in ("jsonb", "json"):
                    logger.info(f"Migrating users.{col} from JSONB to varchar[]")
                    await session.execute(text(
                        f"ALTER TABLE users ALTER COLUMN {col} TYPE varchar[] "
                        f"USING {col}::varchar[];"
                    ))
                    await session.commit()
                    logger.info(f"  → users.{col} migrated to varchar[]")
    except Exception as e:
        logger.warning("Column migration failed: {}", e)

    # Seed data (development only)
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
        logger.warning(f"[Startup] Context auto-reset failed: {e}")

    yield

    logger.info("Shutting down")


from fastapi import FastAPI
app = FastAPI(title="InmuebleBot", lifespan=lifespan)

# ── Health ───────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from app.core.memory import memory_manager
    result = await memory_manager.check_health()
    return {"status": "healthy", "service": "inmueblebot", "redis": result}

@app.get("/health/redis")
async def health_redis():
    from app.core.memory import memory_manager
    result = await memory_manager.check_health()
    return result


# ── Media endpoint (serves property images stored as base64 in DB) ──

# Minimal 1x1 grey JPEG placeholder for fallback (WhatsApp rejects 404 on media URLs)
_PLACEHOLDER_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f'
    b'\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c\x20\x24\x2e\x27\x20\x22\x2c\x23\x1c\x1c\x28\x37\x29\x2c\x30\x31\x34\x34'
    b'\x1f\x27\x39\x3d\x38\x32\x3c\x2e\x33\x34\x32\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xd9'
)


def _detect_mime_from_bytes(raw: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if raw[:2] == b'\xff\xd8':
        return "image/jpeg"
    if raw[:4] == b'\x89PNG':
        return "image/png"
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return "image/webp"
    if raw[:2] in (b'G\x49', b'G\x38'):
        return "image/gif"
    if raw[:4] == b'\x00\x00\x01\x00':
        return "image/x-icon"
    return "image/jpeg"


@app.get("/media/property/{property_id}/{image_index}", include_in_schema=False)
async def serve_property_image(property_id: str, image_index: int):
    """
    Serve a property image as binary.
    Images stored as data:image/...;base64,... in the DB are decoded on-the-fly
    so WhatsApp (which only accepts public HTTPS URLs) can fetch them.
    """
    import base64
    import re
    from fastapi.responses import Response, RedirectResponse
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

            raw = images[image_index]
            if not isinstance(raw, str) or not raw.strip():
                return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

            raw = raw.strip()

            # ── Parse data URI or raw base64 ────────────────────────
            binary = None
            mime = "image/jpeg"

            if raw.startswith("data:"):
                # data:image/xxx;base64,<payload>
                match = re.match(r"data:([^;]+);base64,(.+)", raw, re.DOTALL)
                if match:
                    mime = match.group(1).strip()
                    try:
                        binary = base64.b64decode(match.group(2).strip())
                    except Exception:
                        logger.warning(f"[Media] base64 decode failed for {property_id}/{image_index}")
                        return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
                else:
                    logger.warning(f"[Media] Bad data URI format for {property_id}/{image_index}")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
            elif raw.startswith("http"):
                return RedirectResponse(url=raw)
            else:
                # Raw base64 — detect mime and decode
                try:
                    raw_bytes = base64.b64decode(raw[:120])
                    mime = _detect_mime_from_bytes(raw_bytes)
                    binary = base64.b64decode(raw)
                except Exception:
                    logger.warning(f"[Media] base64 decode failed for {property_id}/{image_index} raw")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

            if binary is None or len(binary) < 100:
                logger.warning(f"[Media] Image too small for {property_id}/{image_index}")
                return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

            # ── Convert WebP → JPEG if needed (WhatsApp restriction) ─
            if mime == "image/webp":
                try:
                    from PIL import Image
                    import io
                    webp_img = Image.open(io.BytesIO(binary))
                    if webp_img.mode == "RGBA":
                        webp_img = webp_img.convert("RGB")
                    jpeg_buf = io.BytesIO()
                    webp_img.save(jpeg_buf, format="JPEG", quality=85)
                    binary = jpeg_buf.getvalue()
                    mime = "image/jpeg"
                except ImportError:
                    logger.warning("[Media] Pillow not installed — serving placeholder for WebP image")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
                except Exception as e:
                    logger.warning(f"[Media] WebP→JPEG conversion failed: {e}")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

            return Response(content=binary, media_type=mime)

    except Exception as e:
        logger.error(f"[Media] Error serving property {property_id} image {image_index}: {e}")
        return Response(status_code=500)


# ── Global Exception Handler ────────────────────────────────────────────────
from fastapi.responses import JSONResponse
from starlette.requests import Request


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions, log them, and return a friendly response."""
    logger.exception(
        "Unhandled exception on %s %s: %s",
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


# ── Static Files ─────────────────────────────────────────────────

# Serve dashboard SPA from dashboard/dist (if exists)
dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "dist")
if os.path.isdir(dashboard_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dashboard_dir, "assets")), name="assets")
    logger.info("Dashboard SPA served from dashboard/dist")
else:
    logger.warning(f"Dashboard dist not found at {dashboard_dir}")


# ── Routers ─────────────────────────────────────────────────────────────────

# WhatsApp webhook
from app.api.routes.webhook import router as webhook_router
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

# Serve dashboard SPA index.html for all unmatched routes
from fastapi.responses import FileResponse
import os

@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard/{full_path:path}", include_in_schema=False)
async def serve_dashboard(full_path: str = ""):
    dashboard_index = os.path.join(dashboard_dir, "index.html")
    if os.path.isfile(dashboard_index):
        return FileResponse(dashboard_index)
    return JSONResponse(status_code=404, content={"detail": "Dashboard not built"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
