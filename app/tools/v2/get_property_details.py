"""Get property details by ID."""

from typing import Any

from sqlalchemy import select

from app.db.session import async_session_factory
from app.db.models.property import Property


async def get_property_details(property_id: int = 0) -> str:
    """Return full details for a specific property by its ID.

    Args:
        property_id: The numeric ID of the property (from search results).
    """
    if not property_id:
        return "Necesito el número de ID de la propiedad. Usá el número que aparece entre corchetes en los resultados de búsqueda, por ejemplo 'mostrame más del 3'."

    async with async_session_factory() as session:
        result = await session.execute(
            select(Property).where(Property.id == property_id)
        )
        prop = result.scalars().first()

        if not prop:
            return f"No encontré ninguna propiedad con ID {property_id}. ¿Revisamos los resultados de búsqueda de nuevo?"

        op_label = "ALQUILER" if prop.type == "alquiler" else "VENTA"
        price_str = (
            f"${prop.price:,.0f} por mes" if prop.type == "alquiler"
            else f"${prop.price:,.0f}"
        )
        tipo_str = (prop.category or "propiedad").capitalize()

        amenities = (prop.extra_data or {}).get("amenities", []) if prop.extra_data else []
        amenities_str = ", ".join(amenities).replace("_", " ") if amenities else ""

        area_str = f"{prop.area_m2:.0f}m² cubiertos" if prop.area_m2 else ""

        lines = [
            f"🏠 {prop.title}",
            "━━━━━━━━━━━━━━━━━━━━",
            f"📋 ID: {prop.id} | {op_label}",
            f"📍 {prop.location}",
            f"💰 {price_str}",
            f"🛏️  {prop.bedrooms} dormitorio{'s' if prop.bedrooms != 1 else ''}"
            f"{' (monoambiente)' if prop.bedrooms == 0 else ''}",
            f"🚿 {int(prop.bathrooms)} baño{'s' if prop.bathrooms != 1 else ''}",
        ]
        if area_str:
            lines.append(f"📐 {area_str}")
        if amenities_str:
            lines.append(f"✨ {amenities_str}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📝 {prop.description}")

        return "\n".join(lines)
