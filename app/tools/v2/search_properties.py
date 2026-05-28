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
    # Map common user terms to stored values (computed early for fallback use)
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
    mapped_tipo = tipo_map.get(tipo.lower(), tipo.lower()) if tipo else ""

    async with async_session_factory() as session:
        stmt = select(Property)

        if operation:
            stmt = stmt.where(Property.type == operation.lower())
        if mapped_tipo:
            stmt = stmt.where(Property.category == mapped_tipo)
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
            # ── Fallback 1: operation + zona ───────────────────────────────
            # Drop tipo / budget / bedrooms and re-query with only operation +
            # zona to see what IS available nearby.
            fallback = select(Property)
            if operation:
                fallback = fallback.where(Property.type == operation.lower())
            if zona:
                fallback = fallback.where(or_(*_build_zone_filters(zona)))

            fallback_result = await session.execute(fallback)
            nearby = fallback_result.scalars().all()

            if nearby:
                # ── Fallback 2: drop zona, keep operation + tipo + dormitorios ──
                # When the user asked for a specific property type near a
                # landmark and Fallback 1 only found OTHER types, try dropping
                # the zona filter and showing matching types in all of Oberá.
                nearby_has_matching_tipo = (
                    not mapped_tipo
                    or any(p.category == mapped_tipo for p in nearby)
                )

                if not nearby_has_matching_tipo:
                    fallback2 = select(Property)
                    if operation:
                        fallback2 = fallback2.where(Property.type == operation.lower())
                    if mapped_tipo:
                        fallback2 = fallback2.where(Property.category == mapped_tipo)
                    if dormitorios > 0:
                        fallback2 = fallback2.where(Property.bedrooms == dormitorios)

                    fb2_result = await session.execute(fallback2)
                    tipo_matches = fb2_result.scalars().all()

                    if tipo_matches:
                        tipo_word = tipo if tipo else "propiedades"
                        dorm_part = (
                            f" de {dormitorios} dormitorio{'s' if dormitorios != 1 else ''}"
                            if dormitorios > 0 else ""
                        )
                        return (
                            f"No encontré {tipo_word}s{dorm_part} específicamente en {zona}. "
                            f"Pero hay {len(tipo_matches)} {tipo_word}s{dorm_part} en otras zonas "
                            f"de Oberá. ¿Querés que te las muestre?"
                        )

                # ── Show Fallback 1 results (nearby summary) ──────────────────
                # Group nearby results by (operation, category)
                counts: dict[tuple[str, str], int] = {}
                for p in nearby:
                    op_label = "alquiler" if p.type == "alquiler" else "venta"
                    key = (op_label, p.category)
                    counts[key] = counts.get(key, 0) + 1

                # Build a natural summary: "2 casas en alquiler, 1 terreno en alquiler, y 1 casa en venta"
                items = []
                for (op, cat), count in sorted(counts.items(), key=lambda x: -x[1]):
                    # Simple pluralisation
                    cat_plural = cat if cat in ("ph",) else cat + ("s" if count != 1 else "")
                    items.append(f"{count} {cat_plural} en {op}")

                if len(items) == 1:
                    summary = items[0]
                elif len(items) == 2:
                    summary = f"{items[0]} y {items[1]}"
                else:
                    summary = ", ".join(items[:-1]) + f", y {items[-1]}"

                tipo_word = tipo if tipo else "propiedades"
                tipo_plural = tipo_word if tipo_word in ("ph",) else tipo_word + ("s" if tipo_word[-1] != "s" else "")
                zona_part = f" en {zona}" if zona else ""

                return (
                    f"No encontré {tipo_plural} en {operation}{zona_part}. "
                    f"Pero hay {len(nearby)} propiedades cerca: "
                    f"{summary}. ¿Querés que te las muestre?"
                )

            # No results at all — keep the original message
            return f"No encontré propiedades{filters_desc}. ¿Querés ajustar algún filtro?"

        lines = [f"Encontré {len(properties)} {_plural('propiedad', len(properties))}{filters_desc}:\n"]
        for p in properties:
            price_str = f"${p.price:,.0f}/mes" if p.type == "alquiler" else f"${p.price:,.0f}"
            tipo_str = p.category.capitalize()
            zone = _extract_zone(p.location)
            beds_str = f"{p.bedrooms} dorm" if p.bedrooms and p.bedrooms > 0 else ""
            area_str = f"{p.area_m2:.0f}m²" if p.area_m2 and p.area_m2 > 0 else ""
            baths_str = f"{int(p.bathrooms)} baño{'s' if p.bathrooms != 1 else ''}" if p.bathrooms and p.bathrooms > 0 else ""
            specs = " · ".join(s for s in [beds_str, baths_str, area_str] if s)

            lines.append(
                f"  [{p.id}] {tipo_str} en {zone} — {price_str}"
            )
            if specs:
                lines.append(f"       {specs}")

        # ── Post-search suggestion ───────────────────────────────────────
        # After showing results, suggest filtering by missing criteria
        missing_tip = _build_missing_criteria_tip(operation, tipo, zona, presupuesto_max, dormitorios)
        if missing_tip:
            lines.append("")
            lines.append(missing_tip)

        return "\n".join(lines)


def _extract_zone(location: str) -> str:
    """Extract neighborhood/zone from a full location string.

    'Calle Dinamarca 1176, Barrio 100 Viviendas, Oberá, Misiones'
    → 'Barrio 100 Viviendas'
    """
    if not location:
        return location
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        zone = parts[1]
        if zone.lower() not in ("oberá", "obera", "misiones"):
            return zone
        return parts[0]
    return parts[0]


def _plural(word: str, count: int) -> str:
    """Return singular or plural form based on count. 1 propiedad / 5 propiedades."""
    if count == 1:
        return word
    return word + "s"


def _build_missing_criteria_tip(
    operation: str, tipo: str, zona: str,
    presupuesto_max: float, dormitorios: int,
) -> str:
    """Suggest filtering by criteria the user hasn't specified yet."""
    missing = []
    if not zona:
        missing.append("zona")
    if not presupuesto_max:
        missing.append("presupuesto")
    if not dormitorios:
        missing.append("dormitorios")

    if not missing:
        return ""

    if len(missing) == 1:
        return f"Si querés, puedo filtrar por {missing[0]}."
    elif len(missing) == 2:
        return f"Si querés, puedo filtrar por {missing[0]} o {missing[1]}."
    else:
        return f"Si querés, puedo filtrar por {missing[0]}, {missing[1]} o {missing[2]}."


def _describe_filters(
    operation: str = "",
    tipo: str = "",
    zona: str = "",
    presupuesto_max: float = 0,
    dormitorios: int = 0,
) -> str:
    """Build a human-readable description of active filters."""
    parts = []
    if tipo:
        parts.append(tipo + ("s" if tipo[-1] != "s" else ""))
    if operation:
        parts.append(f"en {operation}")
    if zona:
        parts.append(f"en {zona}")
    if presupuesto_max > 0:
        parts.append(f"hasta ${presupuesto_max:,.0f}")
    if dormitorios > 0:
        parts.append(f"{dormitorios} dormitorio{'s' if dormitorios > 1 else ''}")

    if not parts:
        return ""
    return " " + ", ".join(parts)
