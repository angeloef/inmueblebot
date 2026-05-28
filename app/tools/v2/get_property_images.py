"""Get property images by ID."""

import json
from typing import Any

from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.property import Property


def _to_public_image_urls(raw_images: list, property_id: int) -> list[str]:
    """Convert data:URIs and localhost URLs to public HTTPS URLs.

    WhatsApp requires publicly-accessible HTTPS URLs — data URIs and
    localhost URLs are silently rejected. The /media/property/{id}/{index}
    endpoint serves base64-encoded images with correct Content-Type headers.
    """
    from app.core.config import get_settings
    base = get_settings().API_BASE_URL.rstrip("/")
    public: list[str] = []
    for i, img in enumerate(raw_images):
        if isinstance(img, str) and (img.startswith("data:") or not img.startswith("http")):
            public.append(f"{base}/media/property/{property_id}/{i}")
        elif isinstance(img, str) and ("localhost" in img or "127.0.0.1" in img):
            public.append(f"{base}/media/property/{property_id}/{i}")
        else:
            public.append(img)
    return public


async def get_property_images(property_id: int = 0) -> str:
    """Return property images as JSON with display_text and public image URLs.

    Returns JSON: {"display_text": "...", "images": [...], "title": "..."}
    The display_text is safe for LLM consumption; images are public HTTPS URLs
    ready for WhatsApp native image sending.
    """
    if not property_id:
        return json.dumps({
            "display_text": "Necesito el número de ID de la propiedad para mostrarte las fotos.",
            "images": [],
            "title": "",
        })

    async with async_session_factory() as session:
        result = await session.execute(
            select(Property).where(Property.id == property_id)
        )
        prop = result.scalars().first()

        if not prop:
            return json.dumps({
                "display_text": f"No encontré ninguna propiedad con ID {property_id}.",
                "images": [],
                "title": "",
            })

        if not prop.images:
            return json.dumps({
                "display_text": f"La propiedad '{prop.title}' todavía no tiene fotos cargadas.",
                "images": [],
                "title": prop.title,
            })

        public_urls = _to_public_image_urls(prop.images, property_id)
        display_text = f"📸 Fotos de '{prop.title}' ({len(public_urls)} imágenes)"

        return json.dumps({
            "display_text": display_text,
            "images": public_urls,
            "title": prop.title,
        })
