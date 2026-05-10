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
        logger.warning("Table creation failed: %s", e)

    try:
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result.fetchall()]
            logger.info("DB tables: %s", tables)
    except Exception as e:
        logger.warning("DB check failed: %s", e)

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
        logger.warning("Column migration failed: %s", e)

    # Seed data (development only)
    try:
        from app.db.seed import seed_properties
        await seed_properties(force=False)
    except Exception as e:
        logger.warning("Seed failed: %s", e)

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

# Proper minimal 1x1 RGB JPEG placeholder (629 bytes) for fallback
# WhatsApp rejects greyscale (1-channel) JPEGs with code 131053
# ("JPG/JPEG, RGB/RGBA, 8 bit/channel"). This is 3-channel RGB.
_PLACEHOLDER_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10\x4a\x46\x49\x46\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00\x43\x00\x10\x0b\x0c\x0e\x0c\x0a\x10\x0e\x0d\x0e\x12\x11\x10\x13\x18\x28\x1a\x18\x16\x16\x18\x31\x23\x25\x1d\x28\x3a\x33\x3d\x3c\x39\x33\x38\x37\x40'
    b'\x48\x5c\x4e\x40\x44\x57\x45\x37\x38\x50\x6d\x51\x57\x5f\x62\x67\x68\x67\x3e\x4d\x71\x79\x70\x64\x78\x5c\x65\x67\x63\xff\xdb\x00\x43\x01\x11\x12\x12\x18\x15\x18\x2f\x1a\x1a\x2f\x63\x42\x38\x42\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63'
    b'\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\x63\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00'
    b'\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01\x7d\x01\x02\x03\x00\x04\x11\x05\x12\x21'
    b'\x31\x41\x06\x13\x51\x61\x07\x22\x71\x14\x32\x81\x91\xa1\x08\x23\x42\xb1\xc1\x15\x52\xd1\xf0\x24\x33\x62\x72\x82\x09\x0a\x16\x17\x18\x19\x1a\x25\x26\x27\x28\x29\x2a\x34\x35\x36\x37\x38\x39\x3a\x43\x44\x45\x46\x47\x48\x49\x4a\x53\x54\x55\x56'
    b'\x57\x58\x59\x5a\x63\x64\x65\x66\x67\x68\x69\x6a\x73\x74\x75\x76\x77\x78\x79\x7a\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6'
    b'\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05'
    b'\x06\x07\x08\x09\x0a\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02\x77\x00\x01\x02\x03\x11\x04\x05\x21\x31\x06\x12\x41\x51\x07\x61\x71\x13\x22\x32\x81\x08\x14\x42\x91\xa1\xb1\xc1\x09\x23\x33\x52\xf0\x15'
    b'\x62\x72\xd1\x0a\x16\x24\x34\xe1\x25\xf1\x17\x18\x19\x1a\x26\x27\x28\x29\x2a\x35\x36\x37\x38\x39\x3a\x43\x44\x45\x46\x47\x48\x49\x4a\x53\x54\x55\x56\x57\x58\x59\x5a\x63\x64\x65\x66\x67\x68\x69\x6a\x73\x74\x75\x76\x77\x78\x79\x7a\x82\x83\x84'
    b'\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea'
    b'\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\x28\xa2\x8a\x00\xff\xd9'
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
@app.head("/media/property/{property_id}/{image_index}", include_in_schema=False)
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
                    # data: URI but regex didn't match — try manual extraction
                    logger.warning(f"[Media] Unusual data URI format for {property_id}/{image_index}")
                    # Fallback: split on first ;base64, or ,base64
                    for sep in (";base64,", ":base64,", ",base64,"):
                        if sep in raw:
                            mime = "image/jpeg"
                            b64_part = raw.split(sep, 1)[1]
                            try:
                                binary = base64.b64decode(b64_part.strip())
                                break
                            except Exception:
                                binary = None
                    if binary is None:
                        logger.warning(f"[Media] Can't parse data URI for {property_id}/{image_index}")
                        return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
            elif raw.startswith("http"):
                # If it's a localhost/internal URL, it won't be accessible from the internet
                # (WhatsApp can't reach localhost / 127.0.0.1). Serve placeholder instead.
                if "localhost" in raw or "127.0.0.1" in raw:
                    logger.warning(f"[Media] localhost URL detected for {property_id}/{image_index} — serving placeholder")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
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

            # OVERRIDE mime with actual magic bytes — don't trust data URI's stated mime
            # (images may be WebP labeled as JPEG/PNG)
            try:
                actual_mime = _detect_mime_from_bytes(binary[:32])
                if actual_mime == "image/jpeg" and binary[:2] == b'\xff\xd8':
                    mime = "image/jpeg"
                elif actual_mime == "image/png" and binary[:4] == b'\x89PNG':
                    mime = "image/png"
                elif actual_mime == "image/webp":
                    mime = "image/webp"
                elif actual_mime == "image/gif":
                    mime = "image/gif"
                else:
                    # Unknown format — serve placeholder
                    logger.warning(f"[Media] Unknown image format for {property_id}/{image_index} (magic={binary[:4].hex()})")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
            except Exception:
                logger.warning(f"[Media] Magic byte detection failed for {property_id}/{image_index}")
                return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

            # ── Convert format to WhatsApp-compatible JPEG if needed ─
            # WhatsApp only accepts image/jpeg and image/png
            if mime in ("image/webp", "image/gif"):
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(binary))
                    if img.mode == "RGBA":
                        img = img.convert("RGB")
                    jpeg_buf = io.BytesIO()
                    img.save(jpeg_buf, format="JPEG", quality=85)
                    binary = jpeg_buf.getvalue()
                    mime = "image/jpeg"
                except ImportError:
                    logger.warning("[Media] Pillow not installed — serving placeholder")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")
                except Exception as e:
                    logger.warning(f"[Media] {mime}→JPEG conversion failed: {e}")
                    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

            # No-cache headers: prevent WhatsApp from caching placeholder JPEGs
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return Response(content=binary, media_type=mime, headers=headers)

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

# Serve static/ directory (placeholder images, favicon, etc.)
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"Static files served from {static_dir}")
else:
    logger.warning(f"Static dir not found at {static_dir}")

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

# Serve dashboard SPA index.html for root and /dashboard/*
from fastapi.responses import FileResponse
import os

@app.get("/", include_in_schema=False)
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
