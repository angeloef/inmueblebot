"""Search properties by criteria -- filters: operation, type, zone, budget, bedrooms."""

from typing import Any

from sqlalchemy import func, or_, select

from app.core.tenancy import resolve_tenant_id
from app.db.session import async_session_factory
from app.db.models.property import Property

# Accent folding done in SQL (no DB extension needed): translate() is built-in and
# IMMUTABLE. We lower() first so accented uppercase (Á) folds via lower()→á→a.
_ACCENTED = "áéíóúüñ"
_PLAIN = "aeiouun"


def _norm_accents(text: str) -> str:
    """Lowercase + strip Spanish accents on the Python side (mirror of the SQL fold)."""
    return (text or "").lower().translate(str.maketrans(_ACCENTED, _PLAIN))


def _zone_like(col, zona: str):
    """Accent- and case-insensitive substring match of ``zona`` against ``col``."""
    folded_col = func.translate(func.lower(col), _ACCENTED, _PLAIN)
    return folded_col.like(f"%{_norm_accents(zona)}%")


def _scoped_select():
    """``select(Property)`` filtered to the current tenant (app-layer wall over RLS)."""
    return select(Property).where(Property.tenant_id == resolve_tenant_id())

# Landmark aliases: users say "cerca de la UNAM" but the DB zone may not
# contain that literal string.
_LANDMARK_ALIASES: dict[str, list[tuple]] = {
    "unam": [
        (Property.location, "%UNAM%"),
        (Property.title, "%UNAM%"),
        (Property.description, "%UNAM%"),
    ],
}


def _apply_bedrooms_filter(stmt, dormitorios: int, dormitorios_max: int, match_mode: str):
    """Apply bedroom filter based on match mode (exact / at_least / range)."""
    if dormitorios <= 0:
        return stmt

    match_mode = match_mode.lower()
    if match_mode == "exact":
        return stmt.where(Property.bedrooms == dormitorios)
    elif match_mode == "at_least":
        return stmt.where(Property.bedrooms >= dormitorios)
    elif match_mode == "range" and dormitorios_max > 0:
        return stmt.where(
            Property.bedrooms >= dormitorios,
            Property.bedrooms <= dormitorios_max,
        )
    else:
        return stmt.where(Property.bedrooms == dormitorios)


def _build_zone_filters(zona: str) -> list:
    """Build WHERE conditions for a zone/landmark search term.

    The zone name lives in the ``title`` ("Departamento en Centro, Oberá") and the
    city tail of ``location``; match BOTH, accent- and case-insensitively, so a
    user/LLM term like "centro" or "obera" hits "Centro" / "Oberá". (Previously this
    only matched ``location`` with a plain ILIKE, so every zone-scoped search — where
    the zone is only in the title, or sent without its accent — returned nothing.)
    """
    filters = [_zone_like(Property.title, zona), _zone_like(Property.location, zona)]

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
    dormitorios_max: int = 0,
    bedrooms_match: str = "exact",
) -> str:
    """Search properties in Obera matching the given filters.

    All filters are optional -- omitted filters match everything.
    bedrooms_match controls dormitorios matching:
      'exact'    -> == dormitorios  (user said "1 habitacion")
      'at_least' -> >= dormitorios  (user said "al menos 2")
      'range'    -> between dormitorios and dormitorios_max (user said "2 a 3")
    Returns a human-readable list of matching properties.
    """
    tipo_map = {
        "departamento": "departamento", "depto": "departamento",
        "departamentos": "departamento", "deptos": "departamento",
        "casa": "casa", "casas": "casa",
        "ph": "ph",
        "terreno": "terreno", "terrenos": "terreno",
    }
    mapped_tipo = tipo_map.get(tipo.lower(), tipo.lower()) if tipo else ""

    async with async_session_factory() as session:
        stmt = _scoped_select()

        if operation:
            stmt = stmt.where(Property.type == operation.lower())
        if mapped_tipo:
            stmt = stmt.where(Property.category == mapped_tipo)
        if zona:
            zone_filters = _build_zone_filters(zona)
            stmt = stmt.where(or_(*zone_filters))
        if presupuesto_max > 0:
            stmt = stmt.where(Property.price <= presupuesto_max)
        stmt = _apply_bedrooms_filter(stmt, dormitorios, dormitorios_max, bedrooms_match)

        result = await session.execute(stmt)
        properties = result.scalars().all()

        filters_desc = _describe_filters(operation, tipo, zona, presupuesto_max, dormitorios)

        if not properties:
            tipo_word = tipo if tipo else "propiedades"
            tipo_plural = tipo_word if tipo_word in ("ph",) else tipo_word + ("s" if tipo_word[-1] != "s" else "")
            zona_part = f" en {zona}" if zona else ""
            op_part = f" de {operation}" if operation else ""

            # Fallback 1: same zone, same operacion, ANY tipo
            # Priority: show what IS available in the requested zone before expanding zones.
            fallback1 = _scoped_select()
            if operation:
                fallback1 = fallback1.where(Property.type == operation.lower())
            if zona:
                fallback1 = fallback1.where(or_(*_build_zone_filters(zona)))

            fb1_result = await session.execute(fallback1)
            nearby = fb1_result.scalars().all()

            if nearby:
                nearby_has_matching_tipo = (
                    not mapped_tipo
                    or any(p.category == mapped_tipo for p in nearby)
                )

                if not nearby_has_matching_tipo and mapped_tipo:
                    # Zone has properties but NOT the requested type — show what's there.
                    other_tipos = sorted(set(p.category for p in nearby))
                    alt_plural = " y ".join(
                        t if t in ("ph",) else t + ("s" if t[-1] != "s" else "")
                        for t in other_tipos[:2]
                    )
                    header = (
                        f"No tenemos {tipo_plural}{op_part}{zona_part}. "
                        f"Pero encontré {len(nearby)} {alt_plural}{op_part} en {zona or 'Oberá'}:"
                    )
                    return header + "\n\n" + _format_properties_list(nearby, operation)

                elif mapped_tipo and nearby_has_matching_tipo:
                    # Zone has the right tipo but different bedrooms/criteria.
                    # E1 fix: don't duplicate tipo in header (tipo_plural already names it).
                    # E4 fix: filter to show ONLY matching tipo — no mixed depto/terreno/casa.
                    tipo_nearby = [p for p in nearby if p.category == mapped_tipo]
                    dorm_part = (
                        f", {dormitorios} dormitorio{'s' if dormitorios != 1 else ''}"
                        if dormitorios > 0 else ""
                    )
                    header = (
                        f"No encontré {tipo_plural}{op_part}{zona_part}{dorm_part}. "
                        f"Hay {len(tipo_nearby)} {tipo_plural} disponibles{zona_part}:"
                    )
                    return header + "\n\n" + _format_properties_list(tipo_nearby, operation)

                else:
                    # No tipo filter — show all available types in zone.
                    filters_no_tipo = _describe_filters(operation, "", zona, presupuesto_max, dormitorios)
                    header = (
                        f"No encontré propiedades{filters_no_tipo}. "
                        f"Opciones disponibles{zona_part}:"
                    )
                    return header + "\n\n" + _format_properties_list(nearby, operation)

            # Fallback 2: drop zona, keep tipo + operacion (other zones, same tipo)
            # Only reached when the zone has ZERO properties of any type.
            if zona and (operation or mapped_tipo):
                fb2 = _scoped_select()
                if operation:
                    fb2 = fb2.where(Property.type == operation.lower())
                if mapped_tipo:
                    fb2 = fb2.where(Property.category == mapped_tipo)
                fb2 = _apply_bedrooms_filter(fb2, dormitorios, dormitorios_max, bedrooms_match)

                fb2_result = await session.execute(fb2)
                tipo_matches = fb2_result.scalars().all()

                if tipo_matches:
                    dorm_part = (
                        f" de {dormitorios} dormitorio{'s' if dormitorios != 1 else ''}"
                        if dormitorios > 0 else ""
                    )
                    return (
                        f"No encontre {tipo_plural}{dorm_part} especificamente en {zona}. "
                        f"Pero hay {len(tipo_matches)} {tipo_plural}{dorm_part} en otras zonas "
                        f"de Obera. Queres que te las muestre?"
                    )

            # Fallback 3: drop zona, show anything matching operacion + tipo
            if zona and (operation or mapped_tipo or presupuesto_max > 0 or dormitorios > 0):
                fb3 = _scoped_select()
                if operation:
                    fb3 = fb3.where(Property.type == operation.lower())
                if mapped_tipo:
                    fb3 = fb3.where(Property.category == mapped_tipo)
                if presupuesto_max > 0:
                    fb3 = fb3.where(Property.price <= presupuesto_max)
                fb3 = _apply_bedrooms_filter(fb3, dormitorios, dormitorios_max, bedrooms_match)

                fb3_result = await session.execute(fb3)
                no_zone_results = fb3_result.scalars().all()

                if no_zone_results:
                    return (
                        f"No se encontraron propiedades en '{zona}'. "
                        f"Mostrando propiedades similares en otras zonas de Obera:\n"
                        f"\n{_format_properties_list(no_zone_results, operation, presupuesto_max)}"
                    )

            return f"No encontre propiedades{filters_desc}. Queres ajustar algun filtro?"

        lines = [f"Encontre {len(properties)} {_plural('propiedad', len(properties))}{filters_desc}:\n"]
        for p in properties:
            price_str = f"${p.price:,.0f}/mes" if p.type == "alquiler" else f"${p.price:,.0f}"
            tipo_str = p.category.capitalize()
            zone = _extract_zone(p.location)
            beds_str = f"{p.bedrooms} dorm" if p.bedrooms and p.bedrooms > 0 else ""
            area_str = f"{p.area_m2:.0f}m2" if p.area_m2 and p.area_m2 > 0 else ""
            baths_str = f"{int(p.bathrooms)} bano{'s' if p.bathrooms != 1 else ''}" if p.bathrooms and p.bathrooms > 0 else ""
            specs = " | ".join(s for s in [beds_str, baths_str, area_str] if s)

            lines.append(f"  [{p.id}] {tipo_str} en {zone} -- {price_str}")
            if specs:
                lines.append(f"       {specs}")

        missing_tip = _build_missing_criteria_tip(operation, tipo, zona, presupuesto_max, dormitorios)
        if missing_tip:
            lines.append("")
            lines.append(missing_tip)

        return "\n".join(lines)


def _format_properties_list(properties: list, op: str = "", max_price: float = 0) -> str:
    """Format a list of properties as text lines."""
    lines = []
    for p in properties:
        price_str = f"${p.price:,.0f}/mes" if p.type == "alquiler" else f"${p.price:,.0f}"
        tipo_str = p.category.capitalize()
        zone = _extract_zone(p.location)
        beds_str = f"{p.bedrooms} dorm" if p.bedrooms and p.bedrooms > 0 else ""
        area_str = f"{p.area_m2:.0f}m2" if p.area_m2 and p.area_m2 > 0 else ""
        baths_str = f"{int(p.bathrooms)} bano{'s' if p.bathrooms != 1 else ''}" if p.bathrooms and p.bathrooms > 0 else ""
        specs = " | ".join(s for s in [beds_str, baths_str, area_str] if s)
        lines.append(f"  [{p.id}] {tipo_str} en {zone} -- {price_str}")
        if specs:
            lines.append(f"       {specs}")
    return "\n".join(lines)


def _extract_zone(location: str) -> str:
    """Extract neighborhood/zone from a full location string."""
    if not location:
        return location
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        zone = parts[1]
        if zone.lower() not in ("obera", "obera", "misiones"):
            return zone
        return parts[0]
    return parts[0]


def _plural(word: str, count: int) -> str:
    if count == 1:
        return word
    return word + "s"


def _build_missing_criteria_tip(
    operation: str, tipo: str, zona: str,
    presupuesto_max: float, dormitorios: int,
) -> str:
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
        return f"Si queres, puedo filtrar por {missing[0]}."
    elif len(missing) == 2:
        return f"Si queres, puedo filtrar por {missing[0]} o {missing[1]}."
    else:
        return f"Si queres, puedo filtrar por {missing[0]}, {missing[1]} o {missing[2]}."


def _describe_filters(
    operation: str = "",
    tipo: str = "",
    zona: str = "",
    presupuesto_max: float = 0,
    dormitorios: int = 0,
) -> str:
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
