"""Search properties by criteria -- filters: operation, type, zone, budget, bedrooms."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Text, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.tenancy import resolve_tenant_id
from app.db.session import async_session_factory
from app.db.models.property import Property
from app.db.models.user_episode import ZoneStat, SearchFailure
from app.tools.v2.city_resolver import resolve_city_variants

# Accent folding done in SQL (no DB extension needed): translate() is built-in and
# IMMUTABLE. We lower() first so accented uppercase (Á) folds via lower()→á→a.
_ACCENTED = "áéíóúüñ"
_PLAIN = "aeiouun"


def _norm_accents(text: str) -> str:
    """Lowercase + strip Spanish accents on the Python side (mirror of the SQL fold)."""
    return (text or "").lower().translate(str.maketrans(_ACCENTED, _PLAIN))


# Proximity phrases the LLM sometimes leaves glued to a landmark, e.g. the user
# says "cerca de la municipalidad" and the whole phrase arrives as ``zona``. The
# match is substring, so "cerca de la municipalidad" never hits "Municipalidad de
# Oberá". Strip the leading proximity prefix so only the landmark noun remains.
import re as _re

_PROXIMITY_PREFIX = _re.compile(
    r"^\s*(?:"
    r"cerca\s+(?:de\b\s*)?(?:la|el|los|las|del)?\s*|"
    r"a\s+\d+\s+cuadras?\s+(?:de\b\s*)?(?:la|el|del)?\s*|"
    r"(?:por\s+)?la\s+zona\s+de\s+(?:la|el|del)?\s*|"
    r"frente\s+al?\s+(?:la|el)?\s*|"
    r"junto\s+al?\s+(?:la|el)?\s*"
    r")",
    _re.IGNORECASE,
)


def _strip_proximity(zona: str) -> str:
    """Remove a leading 'cerca de la / a 2 cuadras del / frente a' prefix from ``zona``."""
    if not zona:
        return zona
    stripped = _PROXIMITY_PREFIX.sub("", zona).strip()
    # Never return empty (e.g. zona was only "cerca de") — keep the original.
    return stripped or zona


# When a search returns this many or more matches, we ask for the next unknown
# filter (zona → dormitorios → presupuesto) instead of dumping a long list. The
# list is only shown once it narrows below this threshold.
_MAX_LIST = 8

_TIPO_MAP = {
    "departamento": "departamento", "depto": "departamento",
    "departamentos": "departamento", "deptos": "departamento",
    "casa": "casa", "casas": "casa",
    "ph": "ph",
    "terreno": "terreno", "terrenos": "terreno",
}


def _parse_tipos(tipo: str) -> list[str]:
    """Parse a (possibly CSV) ``tipo`` arg into a deduped list of canonical categories.

    "departamento" -> ["departamento"]; "depto,casa,casa" -> ["departamento", "casa"];
    unrecognized terms pass through lowercased rather than being dropped, so an
    exact `Property.category` match still works if the DB has that value; empty
    terms are discarded.
    """
    seen: list[str] = []
    # ponytail: cap terms so a degenerate CSV can't grow the IN(...) clause unbounded.
    for term in (tipo or "").split(",")[:10]:
        term = term.strip().lower()
        if not term:
            continue
        mapped = _TIPO_MAP.get(term, term)
        if mapped not in seen:
            seen.append(mapped)
    return seen


def _tipo_plural_label(tipos: list[str]) -> str:
    """Pluralized display label for 0+ property types, e.g. 'casas' or 'departamentos y casas'."""
    if not tipos:
        return "propiedades"
    words = [t if t == "ph" else t + ("s" if t[-1] != "s" else "") for t in tipos]
    return " y ".join(words)


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
        return f"Encontré {count} opciones en {zona}. ¿Cuántos ambientes o dormitorios buscás? (ej: '2 ambientes', 'monoambiente', '1 dormitorio')"
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
        return stmt.where(Property.bedrooms >= dormitorios, Property.bedrooms <= dormitorios_max)
    return stmt.where(Property.bedrooms == dormitorios)


def _apply_ambientes_filter(stmt, ambientes: int, ambientes_max: int, match_mode: str):
    """Apply ambientes filter (AR: total rooms incl. living; 1=monoambiente)."""
    if ambientes <= 0:
        return stmt
    match_mode = match_mode.lower()
    if match_mode == "exact":
        return stmt.where(Property.ambientes == ambientes)
    elif match_mode == "at_least":
        return stmt.where(Property.ambientes >= ambientes)
    elif match_mode == "range" and ambientes_max > 0:
        return stmt.where(Property.ambientes >= ambientes, Property.ambientes <= ambientes_max)
    return stmt.where(Property.ambientes == ambientes)


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


async def _record_search_telemetry(
    operation: str,
    tipo: str,
    zona: str,
    presupuesto_max: float,
    result_count: int,
) -> None:
    tid = resolve_tenant_id()
    try:
        async with async_session_factory() as session:
            if zona:
                zs = pg_insert(ZoneStat).values(
                    tenant_id=tid, zone_name=zona[:50],
                    search_count=1, property_count=result_count,
                ).on_conflict_do_update(
                    index_elements=["tenant_id", "zone_name"],
                    set_={
                        "search_count": ZoneStat.search_count + 1,
                        "property_count": result_count,
                    },
                )
                await session.execute(zs)

            if result_count == 0:
                now = datetime.now(timezone.utc)
                sf = pg_insert(SearchFailure).values(
                    tenant_id=tid,
                    operation=(operation or "")[:20],
                    property_type=(tipo or "")[:30],
                    zone=(zona or "")[:50],
                    budget_max=int(presupuesto_max) if presupuesto_max else None,
                    fail_count=1, last_failed_at=now,
                ).on_conflict_do_update(
                    index_elements=["tenant_id", "operation", "property_type", "zone"],
                    set_={
                        "fail_count": SearchFailure.fail_count + 1,
                        "last_failed_at": now,
                        "budget_max": int(presupuesto_max) if presupuesto_max else None,
                    },
                )
                await session.execute(sf)

            await session.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).warning("search telemetry write failed", exc_info=True)


async def search_properties(
    operation: str = "",
    tipo: str = "",
    zona: str = "",
    presupuesto_max: float = 0,
    dormitorios: int = 0,
    dormitorios_max: int = 0,
    bedrooms_match: str = "exact",
    ambientes: int = 0,
    ambientes_max: int = 0,
    ambientes_match: str = "exact",
) -> str:
    """Search the current tenant's properties matching the given filters.

    All filters are optional -- omitted filters match everything.
    tipo accepts multiple comma-separated values (e.g. "departamento,casa") to
    match either type in one call.
    bedrooms_match controls dormitorios matching:
      'exact'    -> == dormitorios  (user said "1 habitacion")
      'at_least' -> >= dormitorios  (user said "al menos 2")
      'range'    -> between dormitorios and dormitorios_max (user said "2 a 3")
    Returns a human-readable list of matching properties.
    """
    mapped_tipos = _parse_tipos(tipo)

    # Tenant-aware city/zone labels (no longer hardcoded to Oberá).
    from app.routers.v3.tenant_profile import load_tenant_profile
    _profile = await load_tenant_profile(resolve_tenant_id())
    city = _profile.city or "la zona"
    skip_tokens = frozenset(
        t.lower() for t in (_profile.city, _profile.region, _profile.country) if t
    )

    # Strip proximity prefixes ("cerca de la municipalidad" -> "municipalidad") so a
    # landmark search matches reference_points instead of hitting zero on the raw phrase.
    zona = _strip_proximity(zona)

    # Resolve city spelling variants once (code + LLM) for the zona term.
    city_variants: list[str] = []
    if zona:
        city_variants = await resolve_city_variants(zona)

    async with async_session_factory() as session:
        stmt = _scoped_select()

        if operation:
            stmt = stmt.where(Property.type == operation.lower())
        if mapped_tipos:
            stmt = stmt.where(Property.category.in_(mapped_tipos))
        if zona:
            zone_filters = _build_zone_filters(zona, city_variants)
            stmt = stmt.where(or_(*zone_filters))
        if presupuesto_max > 0:
            stmt = stmt.where(Property.price <= presupuesto_max)
        stmt = _apply_bedrooms_filter(stmt, dormitorios, dormitorios_max, bedrooms_match)
        stmt = _apply_ambientes_filter(stmt, ambientes, ambientes_max, ambientes_match)

        result = await session.execute(stmt)
        properties = result.scalars().all()

        await _record_search_telemetry(operation, tipo, zona, presupuesto_max or 0, len(properties))

        filters_desc = _describe_filters(operation, tipo, zona, presupuesto_max, dormitorios)

        if not properties:
            tipo_plural = _tipo_plural_label(mapped_tipos)
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
                    not mapped_tipos
                    or any(p.category in mapped_tipos for p in nearby)
                )

                if not nearby_has_matching_tipo and mapped_tipos:
                    # Decision: offer the SAME type(s) in nearby zones FIRST. Never dump
                    # other types (casa/terreno) unprompted — ask before showing them.
                    same_elsewhere = await _count_same_type_elsewhere(
                        operation, mapped_tipos,
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

                elif mapped_tipos and nearby_has_matching_tipo:
                    # Zone has the right tipo(s) but different bedrooms/criteria.
                    # E1 fix: don't duplicate tipo in header (tipo_plural already names it).
                    # E4 fix: filter to show ONLY matching tipo(s) — no mixed depto/terreno/casa.
                    tipo_nearby = [p for p in nearby if p.category in mapped_tipos]
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
            if zona and (operation or mapped_tipos):
                fb2 = _scoped_select()
                if operation:
                    fb2 = fb2.where(Property.type == operation.lower())
                if mapped_tipos:
                    fb2 = fb2.where(Property.category.in_(mapped_tipos))
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
            if zona and (operation or mapped_tipos or presupuesto_max > 0 or dormitorios > 0):
                fb3 = _scoped_select()
                if operation:
                    fb3 = fb3.where(Property.type == operation.lower())
                if mapped_tipos:
                    fb3 = fb3.where(Property.category.in_(mapped_tipos))
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
    operation: str, mapped_tipos: list[str],
    dormitorios: int, dormitorios_max: int, bedrooms_match: str,
) -> int:
    """Count tenant properties of the requested type(s)/operation in ANY zone.

    Used to offer "same type in other zones" before ever showing a different type.
    Opens its own session so it never shares/contends with the caller's session.
    """
    stmt = select(func.count()).select_from(Property).where(
        Property.tenant_id == resolve_tenant_id()
    )
    if operation:
        stmt = stmt.where(Property.type == operation.lower())
    if mapped_tipos:
        stmt = stmt.where(Property.category.in_(mapped_tipos))
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
        amb = p.ambientes
        beds = p.bedrooms
        if amb is not None:
            beds_str = "monoambiente" if amb == 1 else f"{amb} amb / {beds} dorm" if beds and beds > 0 else f"{amb} amb"
        else:
            beds_str = f"{beds} dorm" if beds and beds > 0 else ""
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
        parts.append(_tipo_plural_label(_parse_tipos(tipo)))
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
