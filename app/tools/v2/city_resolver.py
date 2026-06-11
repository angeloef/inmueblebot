"""City spelling-variant resolver for search-time matching.

Strategy: resolve at search time — never canonicalize stored data.
Given a user's city term (e.g. "Alem", "LN Alem", "leandro n alem"), return ALL
stored city strings (exact DB spelling) that refer to the same place, using:
  1. Code matcher (free): substring + token-overlap — handles most cases.
  2. LLM matcher: catches abbreviations & uncommon variants the code misses.
The union of both is returned, preserving insertion order (code hits first).
"""
import logging
from typing import Optional

from sqlalchemy import func, select

from app.core.tenancy import resolve_tenant_id
from app.db.models.property import Property
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# Mirror of the accent-folding in search_properties.py
_ACCENTED = "áéíóúüñ"
_PLAIN = "aeiouun"

# Cap the city list sent to the LLM to bound prompt size for tenants with many
# distinct city spellings. Real tenants operate in a handful of cities; this is a
# safety bound, not an expected limit. Code-matched cities are always kept first
# so the cap never drops an already-found candidate.
_MAX_LLM_CITIES = 80


def _fold(s: str) -> str:
    """Lowercase + accent-fold + strip (mirrors SQL translate())."""
    return (s or "").lower().translate(str.maketrans(_ACCENTED, _PLAIN)).strip()


async def _distinct_tenant_cities() -> list[str]:
    """Return distinct exact city strings from extra_data['city'] for the current tenant."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.distinct(Property.extra_data["city"].astext)).where(
                Property.tenant_id == resolve_tenant_id()
            )
        )
        return [
            str(row[0]).strip()
            for row in result
            if row[0] and str(row[0]).strip()
        ]


def _code_match(term: str, cities: list[str]) -> list[str]:
    """Free code-based matcher: substring + token-overlap (accent-folded, case-insensitive)."""
    folded_term = _fold(term)
    if not folded_term:
        return []

    # Tokenize: split on whitespace and replace "." with " " before splitting
    def _tokens(s: str) -> set[str]:
        return {t for t in _fold(s).replace(".", " ").split() if len(t) > 2}

    term_tokens = _tokens(term)
    matches: list[str] = []
    for city in cities:
        fc = _fold(city)
        # Substring check (either direction)
        if folded_term in fc or fc in folded_term:
            matches.append(city)
            continue
        # Token-overlap check
        if term_tokens & _tokens(city):
            matches.append(city)
    return matches


_LLM_SYSTEM_PROMPT = (
    "Sos un resolvedor de ciudades para un sistema de bienes raíces en Argentina y Paraguay.\n"
    "Recibirás:\n"
    "  1. Una lista de ciudades (exactamente como están guardadas en la base de datos).\n"
    "  2. El término que usó el usuario.\n\n"
    "Tu tarea: devolver SOLO las ciudades de la lista que se refieren al mismo lugar que el "
    "término del usuario, incluyendo variantes de escritura y abreviaturas "
    "(por ejemplo: 'Alem', 'LN Alem', 'Leandro N. Alem' son el mismo lugar).\n\n"
    "Reglas:\n"
    "- Copiá cada ciudad que coincida EXACTAMENTE como aparece en la lista, una por línea.\n"
    "- Si ninguna coincide, respondé exactamente: NONE\n"
    "- No des explicaciones. No agregues texto extra."
)


async def _llm_match(term: str, cities: list[str]) -> list[str]:
    """LLM-based matcher: catches abbreviations and non-obvious spelling variants."""
    if not cities:
        return []
    from app.agents.llm_router import llm_router

    city_list_str = "\n".join(f"- {c}" for c in cities)
    message = f"Ciudades disponibles:\n{city_list_str}\n\nTérmino del usuario: {term}"

    result_str, _ = await llm_router.chat(
        message=message,
        system_prompt=_LLM_SYSTEM_PROMPT,
        max_completion_tokens=120,
        return_usage=True,
    )

    result_str = (result_str or "").strip()
    if not result_str or result_str.upper() == "NONE":
        return []

    # Build a folded lookup dict for exact-case recovery
    folded_to_exact: dict[str, str] = {_fold(c): c for c in cities}

    matched: list[str] = []
    for line in result_str.splitlines():
        # Strip leading list markers (- or •)
        clean = line.strip().lstrip("-•").strip()
        if not clean:
            continue
        # Look up by folded value to recover the exact DB spelling
        key = _fold(clean)
        if key in folded_to_exact:
            matched.append(folded_to_exact[key])

    return matched


async def resolve_city_variants(term: str) -> list[str]:
    """Return all stored city spellings (exact DB strings) that refer to the same place as `term`.

    Returns an empty list when term is blank or no cities exist for this tenant.
    Code matches come first; LLM matches are appended (deduped).
    """
    if not (term or "").strip():
        return []

    cities = await _distinct_tenant_cities()
    if not cities:
        return []

    code_hits = _code_match(term, cities)

    # LLM disambiguation only when it can actually add something: more than one
    # distinct city exists AND the code matcher didn't already match them all.
    # We still run it when code found a *strict subset* — that preserves recall
    # (e.g. "leandro" matches "Leandro N. Alem" by code, but the LLM also recovers
    # "Alem" and "LN Alem", which share no >2-char token with the query).
    llm_hits: list[str] = []
    if len(cities) > 1 and len(code_hits) < len(cities):
        # Put code-matched cities first so the size cap never drops a known candidate.
        candidates = list(dict.fromkeys(code_hits + cities))[:_MAX_LLM_CITIES]
        try:
            llm_hits = await _llm_match(term, candidates)
        except Exception as exc:
            logger.warning("resolve_city_variants: LLM matcher failed for %r: %s", term, exc)

    # Union preserving order: code hits first, then new LLM hits
    return list(dict.fromkeys(code_hits + llm_hits))
