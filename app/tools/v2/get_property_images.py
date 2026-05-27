"""Get property images by ID."""

from typing import Any

from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.property import Property


async def get_property_images(property_id: int = 0) -> str:
    """Return the list of image URLs for a specific property.

    Args:
        property_id: The numeric ID of the property.
    """
    if not property_id:
        return "Necesito el número de ID de la propiedad para mostrarte las fotos."

    async with async_session_factory() as session:
        result = await session.execute(
            select(Property).where(Property.id == property_id)
        )
        prop = result.scalars().first()

        if not prop:
            return f"No encontré ninguna propiedad con ID {property_id}."

        if not prop.images:
            return f"La propiedad '{prop.title}' todavía no tiene fotos cargadas."

        lines = [f"📸 Fotos de '{prop.title}' ({len(prop.images)} imágenes):\n"]
        for i, img in enumerate(prop.images, 1):
            lines.append(f"  [{i}] {img}")

        return "\n".join(lines)
