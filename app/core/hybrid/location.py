"""Location normalization: extract canonical city name from messy descriptions."""
import logging
import re

from .base import HybridParser, ParseResult

logger = logging.getLogger(__name__)

# All known cities/towns in the database.
# Populated from DB on startup via refresh_known_cities(). Fallback static list.
_KNOWN_CITIES: set[str] = {
    "posadas", "obera", "encarnacion", "asuncion", "puerto iguazu",
    "eldorado", "apostoles", "leandro n. alem", "san javier",
    "candelaria", "garupa", "montecarlo", "puerto rico",
    "resistencia", "corrientes", "formosa",
    "ciudad del este", "luque", "lambare", "san lorenzo",
    "fernando de la mora", "capitata", "itaugua", "ypacarai",
}

# Also known accent-variants for matching
_ACCENT_MAP = {
    "oberá": "obera",
    "encarnación": "encarnacion",
    "asunción": "asuncion",
    "iguazú": "iguazu",
    "apóstoles": "apostoles",
    "lambaré": "lambare",
    "itá": "ita",
    "ypacaraí": "ypacarai",
    "capiatá": "capitata",
}


def _code_normalize(raw: str) -> ParseResult:
    """Current regex logic, wrapped in ParseResult."""
    if not raw:
        return ParseResult(None, 0.0, "code")
    raw_lower = raw.lower().strip()
    # Try exact city match first (with accent normalization)
    search_text = raw_lower
    for accented, plain in _ACCENT_MAP.items():
        search_text = search_text.replace(accented, plain)
    for city in _KNOWN_CITIES:
        if city in search_text:
            return ParseResult(city.title(), 0.7, "code")
    # Fallback: strip prefixes + numbers (current logic)
    loc = raw_lower
    from app.utils.sanitizer import _STREET_PREFIXES

    for prefix in _STREET_PREFIXES:
        if loc.startswith(prefix + " ") or loc == prefix:
            loc = loc[len(prefix) :].strip()
            break
    loc = re.sub(r"\s+\d+\s*$", "", loc).strip()
    if loc:
        return ParseResult(loc.title(), 0.3, "code")
    return ParseResult(None, 0.0, "code")


_LOCATION_SYSTEM_PROMPT = (
    "Sos un extractor de ubicaciones para un chatbot de bienes raices en Argentina/Paraguay.\n"
    "Tu unica tarea: extraer ciudad + zona/barrio del texto del usuario.\n\n"
    "Reglas:\n"
    "- Responde SOLO con el nombre de la ciudad, opcionalmente seguido de la zona. Formato: 'Ciudad' o 'Ciudad zona'.\n"
    "- Ej: 'cerca de la terminal de Obera' -> 'Obera terminal'\n"
    "- Ej: 'en el centro de Posadas' -> 'Posadas centro'\n"
    "- Ej: 'zona norte de Encarnacion' -> 'Encarnacion norte'\n"
    "- Ej: 'alquiler en Asuncion cerca del Paseo La Galeria' -> 'Asuncion'\n"
    "- Ej: 'barrio krause obera' -> 'Obera barrio krause'\n"
    "- Ej: 'Posadas centro' -> 'Posadas centro'\n"
    "- Ej: 'Obera' -> 'Obera'\n"
    "- Si no hay ciudad clara -> 'UNKNOWN'.\n"
    "- Usa el nombre completo, no apodos.\n"
    "- MANTENE la zona/barrio cuando el usuario la menciona — no la borres.\n"
    "- No uses acentos.\n"
    "- Nunca des explicaciones."
)


class LocationParser(HybridParser):
    """Extract canonical city name from free-text location descriptions."""

    def __init__(self):
        super().__init__(component="LOCATION", default_strategy="hybrid")

    async def parse_llm(self, raw: str, ctx: dict) -> ParseResult:
        from app.agents.llm_router import llm_router

        if not raw or len(raw.strip()) < 3:
            return ParseResult(None, 0.0, "llm")

        result, usage = await llm_router.chat(
            message=raw,
            system_prompt=_LOCATION_SYSTEM_PROMPT,
            temperature=0,
            max_tokens=20,
            return_usage=True,
        )
        result = (result or "").strip()
        tokens = (usage or {}).get("completion_tokens", 0)

        if not result or result.upper() == "UNKNOWN":
            return ParseResult(None, 0.0, "llm", llm_tokens=tokens)

        return ParseResult(value=result.strip(), confidence=0.9, parser_used="llm", llm_tokens=tokens)

    async def parse_code(self, raw: str, ctx: dict) -> ParseResult:
        return _code_normalize(raw)


async def refresh_known_cities():
    """Pull distinct cities from the properties table at startup."""
    try:
        from sqlalchemy import func, select

        from app.db.models.property import Property
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            # Query distinct locations from the properties table
            result = await session.execute(
                select(func.distinct(func.lower(Property.location)))
            )
            cities = {str(row[0]).strip().lower() for row in result if row[0]}
            if cities:
                _KNOWN_CITIES.clear()
                _KNOWN_CITIES.update(cities)
                logger.info(
                    "refresh_known_cities: %d cities loaded from DB",
                    len(cities),
                )
    except Exception as e:
        logger.warning("refresh_known_cities: DB error (using static list) - %s", e)


location_parser = LocationParser()
