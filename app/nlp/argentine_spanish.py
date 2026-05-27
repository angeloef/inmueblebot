"""Argentine Spanish vocabulary and regional adaptations (Phase 10).

Maps generic Spanish to Argentine real estate terms and provides
vocabulary checks for response quality.
"""

# Argentine-specific real estate vocabulary
ARGENTINE_TERMS = {
    # Property types (Argentine usage)
    "departamento": ["depto", "depa"],
    "casa": ["casa", "casita"],
    "ph": ["ph"],
    "terreno": ["terreno", "lote"],
    
    # Operations
    "alquiler": ["alquiler", "alquilo"],
    "venta": ["venta", "vendo", "compro"],
    
    # Features (Argentine)
    "dormitorios": ["dormitorios", "dormis", "piezas", "habitaciones"],
    "ambientes": ["ambientes", "amb"],
    "cubiertos": ["cubiertos", "cub"],
    "baños": ["baños", "baño"],
    
    # Financial
    "lucas": ["lucas", "mil pesos", "mangos"],
    "palos": ["palos", "millones"],
    "garantía": ["garantía", "garante", "aval"],
    
    # Locations
    "barrio": ["barrio", "zona", "parte"],
    "centro": ["centro", "microcentro"],
    
    # Amenities
    "cochera": ["cochera", "garaje", "estacionamiento"],
    "parrilla": ["parrilla", "asador", "quincho"],
    "patio": ["patio", "fondo", "jardín"],
    "balcón": ["balcón", "balcon", "terraza"],
    "pileta": ["pileta", "piscina", "pelopincho"],
    
    # Actions
    "mostrame": ["mostrame", "mostrá", "enseñame", "pasame"],
    "agendame": ["agendame", "anotame", "coordiname"],
    "buscame": ["buscame", "fijate", "mirá"],
}

# Colloquial Argentine expressions
ARGENTINE_EXPRESSIONS = {
    "greeting_casual": ["hola", "buenas", "qué tal", "cómo va", "todo bien"],
    "agreement": ["dale", "joya", "genial", "buenísimo", "de una", "bárbaro", "espectacular"],
    "thinking": ["a ver", "déjame ver", "bancame un toque", "ahí miro"],
    "apology": ["disculpá", "perdón", "mala mía", "pifiaste"],
    "farewell": ["chau", "nos vemos", "suerte", "abrazo", "cualquier cosa avisame"],
}

# Terms to AVOID (non-Argentine, too formal/foreign)
AVOID_TERMS = [
    "apartamento", "renta", "arriendo", "habitación",
    "vivienda", "inmueble", "residencia", "domicilio",
]


def is_argentine_term(word: str) -> bool:
    """Check if a word is in the Argentine vocabulary."""
    word_lower = word.lower()
    for variants in ARGENTINE_TERMS.values():
        if word_lower in variants:
            return True
    return False


def get_preferred_term(generic: str) -> str:
    """Get the preferred Argentine term for a generic word."""
    generic_lower = generic.lower()
    for preferred, variants in ARGENTINE_TERMS.items():
        if generic_lower in variants or generic_lower == preferred:
            return preferred
    return generic


def check_response_quality(text: str) -> dict:
    """Check a response for Argentine Spanish quality.

    Returns:
        dict with issues found: foreign_terms, missing_voseo, formality_score
    """
    issues = {"foreign_terms": [], "score": 10}

    text_lower = text.lower()

    # Check for foreign/avoid terms
    for term in AVOID_TERMS:
        if term in text_lower:
            issues["foreign_terms"].append(term)
            issues["score"] -= 1

    # Check for Argentine expressions
    arg_score = 0
    for category, expressions in ARGENTINE_EXPRESSIONS.items():
        for expr in expressions:
            if expr in text_lower:
                arg_score += 1
                break
    issues["arg_expression_count"] = arg_score

    # Voseo check (Argentine uses "vos" not "tú")
    words = text_lower.replace("¿", "").replace("?", "").replace("¡", "").replace("!", "").split()
    if "tú" in words or "ti" in words:
        issues["foreign_terms"].append("tuteo (should use voseo)")
        issues["score"] -= 2

    issues["score"] = max(0, min(10, issues["score"] + arg_score))
    return issues


def enrich_with_argentinisms(text: str) -> str:
    """Replace generic terms with Argentine equivalents where possible."""
    result = text
    replacements = {
        "apartamento": "departamento",
        "renta": "alquiler",
        "arriendo": "alquiler",
        "habitación": "dormitorio",
        "habitaciones": "dormitorios",
    }
    for foreign, local in replacements.items():
        result = result.replace(foreign, local)

    return result
