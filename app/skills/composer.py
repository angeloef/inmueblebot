"""Skill composer — chains skills for compound workflows.

Examples:
- search_properties → get_property_details (view result)
- search_properties → compare_properties (compare 2+)
- get_property_details → schedule_visit (view then schedule)
"""

from typing import Optional


# Known skill chains (workflows)
SKILL_CHAINS: dict[str, list[str]] = {
    "search_properties": [
        "get_property_details",
        "get_property_images",
        "compare_properties",
    ],
    "get_property_details": [
        "get_property_images",
        "schedule_visit",
    ],
    "get_property_images": [
        "get_property_details",
        "schedule_visit",
    ],
    "compare_properties": [
        "get_property_details",
        "schedule_visit",
    ],
}


def suggest_next_skills(current_skill: str) -> list[str]:
    """Suggest logical next skills after executing the current one.

    Args:
        current_skill: Name of the skill that was just executed.

    Returns:
        List of skill names that commonly follow this one.
    """
    return SKILL_CHAINS.get(current_skill, [])


def find_similar_skills(query: str) -> list[str]:
    """Find skills whose descriptions match a query string.

    Uses Spanish keyword aliases for common real estate terms.
    """
    from app.skills.registry import get_skill_registry

    registry = get_skill_registry()

    # Spanish → English keyword mapping for skill names
    SPANISH_ALIASES = {
        "buscar": "search_properties",
        "búsqueda": "search_properties",
        "busco": "search_properties",
        "alquilar": "search_properties",
        "comprar": "search_properties",
        "detalles": "get_property_details",
        "detalle": "get_property_details",
        "info": "get_property_details",
        "fotos": "get_property_images",
        "foto": "get_property_images",
        "imágenes": "get_property_images",
        "preguntas": "get_faq_answer",
        "faq": "get_faq_answer",
        "requisitos": "get_faq_answer",
        "garantía": "get_faq_answer",
        "agendar": "schedule_visit",
        "visita": "schedule_visit",
        "coordinar": "schedule_visit",
        "turno": "schedule_visit",
        "comparar": "compare_properties",
        "comparativa": "compare_properties",
    }

    query_lower = query.lower()

    # Direct alias match
    if query_lower in SPANISH_ALIASES:
        return [SPANISH_ALIASES[query_lower]]

    # Word-by-word matching against aliases
    matches = []
    for word in query_lower.split():
        if word in SPANISH_ALIASES:
            matches.append(SPANISH_ALIASES[word])

    if matches:
        return list(dict.fromkeys(matches))  # deduplicate, preserve order

    # Fallback: match against skill descriptions
    for skill in registry.skills.values():
        desc_lower = skill.description.lower()
        if query_lower in desc_lower:
            matches.append(skill.name)

    return matches[:5]
