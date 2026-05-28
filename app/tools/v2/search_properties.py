"""Search properties by criteria — filters: operation, type, zone, budget, bedrooms."""

from typing import Any

from sqlalchemy import or_, select

from app.db.session import async_session_factory
from app.db.models.property import Property

# ── Landmark aliases: users say "cerca de la UNAM" but the DB zone may not
# contain that literal string. This maps known landmarks to the location/zone
# keywords that actually exist in the DB for properties near that landmark.
#
# Extend this dict as new landmarks are identified. The value is a list of
# SQLAlchemy filter conditions expressed as (column, search_term) pairs.
# The first column is the primary match; additional columns broaden recall.
_LANDMARK_ALIASES: dict[str, list[tuple]] = {
    # UNAM (Universidad Nacional de Misiones, Oberá campus) is near the city
    # center. Properties near UNAM may have "UNAM" in title/description but
    # their location field often says "Centro", "Barrio Norte", etc.
    "unam": [
        (Property.location, "%UNAM%"),
        (Property.title, "%UNAM%"),
        (Property.description, "%UNAM%"),
    ],
}


def _build_zone_filters(zona: str) -> list:
    """Build WHERE conditions for a zone/landmark search term.

    1. Exact match via location ILIKE (existing behavior).
    2. If the zone matches a known landmark alias, also search title and
       description for that landmark name — catches properties whose address
       doesn't include the landmark but whose listing text does.
    """
    filters = [Property.location.ilike(f"%{zona}%")]

    # Check landmark aliases (case-insensitive)
    zona_lower = zona.strip().lower()
    if zona_lower in _LANDMARK_ALIASES:
        for col, pattern in _LANDMARK_ALIASES[zona_lower]:
            filters.append(col.ilike(pattern))

    return filters


async def search_properties(
    operation: str = "",
    tipo: str = "",
    zona: str = "",
    presupuesto_max: float = 0,
    dormitorios: int = 0,
) -> str:
    """Search properties in Oberá matching the given filters.

    All filters are optional — omitted filters match everything.
    Returns a human-readable list of matching properties.
    """
    async with async_session_factory() as session:
        stmt = select(Property)

        if operation:
            stmt = stmt.where(Property.type == operation.lower())
        if tipo:
            # Map common user terms to stored values
            tipo_map = {
                "departamento": "departamento",
                "depto": "departamento",
                "departamentos": "departamento",
                "deptos": "departamento",
                "casa": "casa",
                "casas": "casa",
                "ph": "ph",
                "terreno": "terreno",
                "terrenos": "terreno",
            }
            mapped = tipo_map.get(tipo.lower(), tipo.lower())
            stmt = stmt.where(Property.category == mapped)
        if zona:
            zone_filters = _build_zone_filters(zona)
            stmt = stmt.where(or_(*zone_filters))
        if presupuesto_max > 0:
            stmt = stmt.where(Property.price <= presupuesto_max)
        if dormitorios > 0:
            stmt = stmt.where(Property.bedrooms == dormitorios)

        result = await session.execute(stmt)
        properties = result.scalars().all()

        filters_desc = _describe_filters(operation, tipo, zona, presupuesto_max, dormitorios)

        if not properties:
            return f"No encontré propiedades{filters_desc}. ¿Querés ajustar algún filtro?"

        lines = [f"Encontré {len(properties)} propiedades{filters_desc}:\n"]
        for p in properties:
            op_label = "Alquiler" if p.type == "alquiler" else "Venta"
            price_str = f"${p.price:,.0f}/mes" if p.type == "alquiler" else f"${p.price:,.0f}"
            tipo_str = p.category.capitalize()
            bedrooms_str = f"{p.bedrooms} dormitorio{'s' if p.bedrooms != 1 else ''}" if p.bedrooms > 0 else "Monoambiente"

            lines.append(
                f"  [{p.id}] {tipo_str} en {p.location} — {op_label} {price_str}\n"
                f"       {bedrooms_str} | {p.area_m2:.0f}m² | {p.title}"
            )

        return "\n".join(lines)


def _describe_filters(
    operation: str = "",
    tipo: str = "",
    zona: str = "",
    presupuesto_max: float = 0,
    dormitorios: int = 0,
) -> str:
    """Build a human-readable description of active filters."""
    parts = []
    if operation:
        parts.append(f"{operation}")
    if tipo:
        parts.append(tipo)
    if zona:
        parts.append(f"en {zona}")
    if presupuesto_max > 0:
        parts.append(f"hasta ${presupuesto_max:,.0f}")
    if dormitorios > 0:
        parts.append(f"{dormitorios}+ dormitorios")

    if not parts:
        return ""
    return " para " + ", ".join(parts)
