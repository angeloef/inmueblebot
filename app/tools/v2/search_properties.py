"""Search properties by criteria -- filters: operation, type, zone, budget, bedrooms."""

from typing import Any

from sqlalchemy import Text, func, or_, select

from app.core.tenancy import resolve_tenant_id
from app.db.session import async_session_factory
from app.db.models.property import Property
from app.tools.v2.city_resolver import resolve_city_variants

# Accent folding done in SQL (no DB extension needed): translate() is built-in and
# IMMUTABLE. We lower() first so accented uppercase (Á) folds via lower()→á→a.
_ACCENTED = "áéíóúüñ"
_PLAIN = "aeiouun"


def _norm_accents(text: str) -> str:
    """Lowercase + strip Spanish accents on the Python side (mirror of the SQL fold)."""
    return (text or "").lower().translate(str.maketrans(_ACCENTED, _PLAIN))


# When a search returns this many or more matches, we ask for the next unknown
# filter (zona → dormitorios → presupuesto) instead of dumping a long list. The
# list is only shown once it narrows below this threshold.
_MAX_LIST = 8


def _format_price_ars(price: float, is_rental: bool) -> str:
    """Argentine price format: ``$35.976`` (dot = thousands), ``/mes`` only for alquiler."""
    base = f"${price:,.0f}".replace(",", ".")
    return f"{base}/mes" if is_rental else base


def _next_filter_question(
    zona: str, presupuesto_max: float, dormitorios: int, count: int,
) -> str | None:
    """Return a question for the most useful UNKNOWN filter to narrow a large result set.

    Order: zona (narrows most) → dormitorios → presupuesto. Returns None when every
    filter is already known (nothing left to ask — the caller then shows the list).
    """
    if not zona:
        return (
            f"Encontré {count} opciones. Para mostrarte las mejores, ¿en qué zona te gustaría? "
            f"(Centro, UNAM, Barrio Schuster, Ruta 14...)"
        )
    if not dormitorios:
        return f"Encontré {count} opciones en {zona}. ¿Cuántos dormitorios necesitás?"
    if not presupuesto_max:
        return f"Encontré {count} opciones en {zona}. ¿Cuál es tu presupuesto máximo por mes?"
    return None


def _zone_like(col, zona: str):
    """Accent- and case-insensitive substring match of ``zona`` against ``col``."""
    folded_col = func.translate(func.lower(col), _ACCENTED, _PLAIN)
    return folded_col.like(f"%{_norm_accents(zona)}%")


def _city_eq(city: str):
    """Equality match of ``city`` against extra_data['city'] (accent/case-insensitive)."""
    folded_col = func.translate(func.lower(Property.extra_data["city"].astext), _ACCENTED, _PLAIN)
    return folded_col == _norm_accents(city)


def _ref_points_like(term: str):
    """Match ``term`` against any element of the JSONB reference_points array (accent/case-insensitive)."""
    col = func.translate(func.lower(func.cast(Property.reference_points, Text)), _ACCENTED, _PLAIN)
    return col.like(f"%{_norm_accents(term)}%")


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


def _build_zone_filters(zona: str, city_variants: "list[str] | None" = None) -> list:
    """Build WHERE conditions for a zone/landmark search term.

    The zone name lives in the ``title`` ("Departamento en Centro, Oberá") and the
    city tail of ``location``; match BOTH, accent- and case-insensitively, so a
    user/LLM term like "centro" or "obera" hits "Centro" / "Oberá". (Previously this
    only matched ``location`` with a plain ILIKE, so every zone-scoped search — where
    the zone is only in the title, or sent without its accent — returned nothing.)

    city_variants: resolved DB city spellings for ``zona`` (from resolve_city_variants).
    When provided, also matches by exact extra_data['city'] equality and location substring
    for each variant, and against reference_points for the original term.
    """
    filters = [_zone_like(Property.title, zona), _zone_like(Property.location, zona)]

    # reference_points match for the original search term
    filters.append(_ref_points_like(zona))

    # City-variant filters: exact extra_data['city'] equality + location substring
    if city_variants:
        for cv in city_variants:
            filters.append(_zone_like(Property.location, cv))
            filters.append(_city_eq(cv))

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
    """Search the current tenant's properties matching the given filters.

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

    # Tenant-aware city/zone labels (no longer hardcoded to Oberá).
    from app.routers.v3.tenant_profile import load_tenant_profile
    _profile = await load_tenant_profile(resolve_tenant_id())
    city = _profile.city or "la zona"
    skip_tokens = frozenset(
        t.lower() for t in (_profile.city, _profile.region, _profile.country) if t
    )

    # Resolve city spelling variants once (code + LLM) for the zona term.
    city_variants: list[str] = []
    if zona:
        city_variants = await resolve_city_variants(zona)

    async with async_session_factory() as session:
        stmt = _scoped_select()

        if operation:
            stmt = stmt.where(Property.type == operation.lower())
        if mapped_tipo:
            stmt = stmt.where(Property.category == mapped_tipo)
        if zona:
            zone_filters = _build_zone_filters(zona, city_variants)
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
                fallback1 = fallback1.where(or_(*_build_zone_filters(zona, city_variants)))

            fb1_result = await session.execute(fallback1)
            nearby = fb1_result.scalars().all()

            if nearby:
                nearby_has_matching_tipo = (
                    not mapped_tipo
                    or any(p.category == mapped_tipo for p in nearby)
                )

                if not nearby_has_matching_tipo and mapped_tipo:
                    # Decision: offer the SAME type in nearby zones FIRST. Never dump
                    # other types (casa/terreno) unprompted — ask before showing them.
                    same_elsewhere = await _count_same_type_elsewhere(
                        operation, mapped_tipo,
                        dormitorios, dormitorios_max, bedrooms_match,
                    )
                    if same_elsewhere > 0:
                        return (
                            f"No tenemos {tipo_plural}{op_part} en la zona de {zona}. "
                            f"Sí tengo {same_elsewhere} {tipo_plural}{op_part} en otras zonas de {city}. "
                            f"¿Querés que te las muestre?"
                        )
                    # No same-type anywhere — offer other types in the zone, but ask first.
                    other_tipos = sorted(set(p.category for p in nearby))
                    alt_plural = " y ".join(
                        t if t in ("ph",) else t + ("s" if t[-1] != "s" else "")
                        for t in other_tipos[:2]
                    )
                    return (
                        f"No tenemos {tipo_plural}{op_part} en {city} por el momento. "
                        f"En {zona or 'la zona'} sí hay {alt_plural}. ¿Querés ver esas opciones?"
                    )

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
                    return header + "\n\n" + _format_properties_list(tipo_nearby, operation, skip=skip_tokens)

                else:
                    # No tipo filter — show all available types in zone.
                    filters_no_tipo = _describe_filters(operation, "", zona, presupuesto_max, dormitorios)
                    header = (
                        f"No encontré propiedades{filters_no_tipo}. "
                        f"Opciones disponibles{zona_part}:"
                    )
                    return header + "\n\n" + _format_properties_list(nearby, operation, skip=skip_tokens)

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
                        f"No encontré {tipo_plural}{dorm_part} específicamente en {zona}. "
                        f"Pero hay {len(tipo_matches)} {tipo_plural}{dorm_part} en otras zonas "
                        f"de {city}. ¿Querés que te las muestre?"
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
                        f"Mostrando propiedades similares en otras zonas de {city}:\n"
                        f"\n{_format_properties_list(no_zone_results, operation, presupuesto_max, skip=skip_tokens)}"
                    )

            return f"No encontré propiedades{filters_desc}. ¿Querés ajustar algún filtro?"

        # Progressive narrowing: when there are too many matches, ask for the next
        # unknown filter (zona → dormitorios → presupuesto) instead of dumping a long
        # list that gets truncated. Only show the list once it narrows below _MAX_LIST.
        if len(properties) >= _MAX_LIST:
            question = _next_filter_question(zona, presupuesto_max, dormitorios, len(properties))
            if question:
                return question

        lines = [f"Encontré {len(properties)} {_plural('propiedad', len(properties))}{filters_desc}:\n"]
        lines.append(_format_properties_list(properties, operation, skip=skip_tokens))

        missing_tip = _build_missing_criteria_tip(operation, tipo, zona, presupuesto_max, dormitorios)
        if missing_tip:
            lines.append("")
            lines.append(missing_tip)

        return "\n".join(lines)


async def _count_same_type_elsewhere(
    operation: str, mapped_tipo: str,
    dormitorios: int, dormitorios_max: int, bedrooms_match: str,
) -> int:
    """Count tenant properties of the requested type/operation in ANY zone.

    Used to offer "same type in other zones" before ever showing a different type.
    Opens its own session so it never shares/contends with the caller's session.
    """
    stmt = select(func.count()).select_from(Property).where(
        Property.tenant_id == resolve_tenant_id()
    )
    if operation:
        stmt = stmt.where(Property.type == operation.lower())
    if mapped_tipo:
        stmt = stmt.where(Property.category == mapped_tipo)
    stmt = _apply_bedrooms_filter(stmt, dormitorios, dormitorios_max, bedrooms_match)
    async with async_session_factory() as session:
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)


def _format_properties_list(
    properties: list, op: str = "", max_price: float = 0,
    skip: "frozenset[str] | None" = None,
) -> str:
    """Format a list of properties as text lines (Argentine prices, normalized 'ID:N')."""
    lines = []
    for p in properties:
        price_str = _format_price_ars(p.price, p.type == "alquiler")
        tipo_str = p.category.capitalize()
        zone = _extract_zone(p.location, skip)
        beds_str = f"{p.bedrooms} dorm" if p.bedrooms and p.bedrooms > 0 else ""
        area_str = f"{p.area_m2:.0f} m²" if p.area_m2 and p.area_m2 > 0 else ""
        baths_str = f"{int(p.bathrooms)} baño{'s' if p.bathrooms != 1 else ''}" if p.bathrooms and p.bathrooms > 0 else ""
        specs = " | ".join(s for s in [beds_str, baths_str, area_str] if s)
        lines.append(f"  ID:{p.id} — {tipo_str} en {zone} — {price_str}")
        if specs:
            lines.append(f"     {specs}")
    return "\n".join(lines)


def _extract_zone(location: str, skip: "frozenset[str] | None" = None) -> str:
    """Extract the neighborhood/zone from a full location string.

    ``skip`` is a set of lowercased city/region tokens to skip (so the city itself
    isn't shown as the "zone"). Tenant-aware — no longer hardcoded to Oberá/Misiones.
    """
    if not location:
        return location
    skip = skip or frozenset()
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        zone = parts[1]
        if zone.lower() not in skip:
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
