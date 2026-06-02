"""State transitioner — extracts entities from messages and updates belief state.

Replaces hardcoded transitions with regex-based entity extraction
that accumulates criteria across turns.
"""

import re
import time
from app.core.belief_state import ConversationBeliefState
from app.core.config import get_settings


# ── Entity extractors ────────────────────────────────────────

OPERATION_PATTERNS = [
    (r"\b(alquiler|alquilar|rentar|alquilamos)\b", "alquiler"),
    (r"\b(venta|comprar|vender|compramos?)\b", "venta"),
]

TYPE_PATTERNS = [
    (r"\b(departamento|depto|depa|departamentos|deptos)\b", "departamento"),
    (r"\b(casa|casas|casita)\b", "casa"),
    (r"\b(ph)\b", "ph"),
    (r"\b(terreno|lote|terrenos|lotes)\b", "terreno"),
]

# Maps type tokens found in last_search_context to canonical property_type values
_CONTEXT_TYPE_TOKENS = {
    "departamento": "departamento",
    "depto": "departamento",
    "casa": "casa",
    "ph": "ph",
    "terreno": "terreno",
    "lote": "terreno",
    "monoambiente": "departamento",
}


def _property_type_from_context(context: str, prop_id: int) -> str | None:
    """Parse the property type for a given ID out of last_search_context.

    last_search_context entries look like:
      "[44] Casa en UNAM (Alquiler $143,515) — Casa 5 amb"
    Returns the canonical type string, or None if not parseable.
    """
    if not context:
        return None
    m = re.search(rf"\[{prop_id}\]\s+([A-Za-zÀ-ɏ]+)", context)
    if not m:
        return None
    token = m.group(1).strip().lower()
    return _CONTEXT_TYPE_TOKENS.get(token)


ZONE_PATTERNS = [
    (r"\b(centro)\b", "Centro"),
    (r"\b(unam|universidad|facultad)\b", "UNAM"),
    (r"\b(schuster|barrio schuster)\b", "Barrio Schuster"),
    (r"\b(ruta 14|ruta catorce)\b", "Ruta 14"),
    (r"\b(100 viviendas?|cien viviendas?|barrio 100)\b", "Barrio 100 Viviendas"),
    (r"\b(copisa|barrio copisa)\b", "Barrio Copisa"),
    (r"\b(docente|barrio docente)\b", "Barrio Docente"),
    (r"\b(krause|barrio krause)\b", "Barrio Krause"),
    (r"\b(las palmas|barrio las palmas)\b", "Barrio Las Palmas"),
    (r"\b(barrio norte)\b", "Barrio Norte"),
    (r"\b(san miguel|barrio san miguel)\b", "Barrio San Miguel"),
    (r"\b(samic|hospital samic)\b", "Hospital Samic"),
    (r"\b(terminal|barrio terminal|zona terminal)\b", "Terminal"),
    (r"\b(stemberg|villa stemberg)\b", "Villa Stemberg"),
]

BUDGET_PATTERN = re.compile(
    r"(?:hasta|máximo|max|presupuesto de|hasta unos?|no más de|menos de|valga menos de|valga hasta|por menos de|no supere los?)\s*\$?\s*([\d.,]+\s*(?:mil|k|lucas|millones|palos)?)",
    re.IGNORECASE,
)
BEDROOMS_PATTERN = re.compile(
    r"(\d+)\s*(?:dormitorios?|dormi|habitaciones?|ambientes?)",
    re.IGNORECASE,
)

# ── Scheduling data extractors ─────────────────────────────────

NAME_PATTERN = re.compile(
    r"\b(?:me llamo|mi nombre es|soy|me dicen)\s+([A-Za-záéíóúüñÁÉÍÓÚÜÑ\s]+?)(?:\s*[,.]?\s*(?:y|puedo|quiero|quisiera|me|mañana|tarde|\d)|[,.]|$)",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"\b(\+?\d{2,4}\s*\d{3,4}\s*\d{4,6}|\d{3,4}[-.]?\d{4}[-.]?\d{4}|\d{7,12})\b",
)

DAY_PATTERN = re.compile(
    r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|pasado ma[nñ]ana|"
    r"(?:dentro de|en)\s+\d+\s+d[ií]as?|ma[nñ]ana)\b",
    re.IGNORECASE,
)

TIME_PATTERN = re.compile(
    r"((?:a las|las)\s*\d{1,2}(?:[:h]\d{2})?(?:\s*y\s*media)?(?:\s*de la\s*(?:ma[nñ]ana|tarde|noche))?"
    r"|\d{1,2}[:h]\d{2}"
    r"|\d{1,2}\s*de la\s*(?:ma[nñ]ana|tarde|noche)"
    r"|\d{1,2}\s*(?:am|pm|hs)"
    r"|mediod[ií]a|ma[nñ]ana|tarde|noche)",
    re.IGNORECASE,
)

INTENT_PATTERNS = [
    (r"\b(busco|quiero|necesito|buscando|estoy buscando|me interesa)\b", "searching"),
    (r"\b(?:cu[aá]ndo|cuando)\s+(?:puedo|podemos|podr[ií]a|podria)\s+(?:ir|pasar|caer|ver|visitar|conocer)\b", "scheduling"),
    (r"\b(?:quiero|quisiera|me\s+gustar[ií]a)\s+(?:ir|pasar|ver|visitar|conocer|coordinar)\b", "scheduling"),
    (r"\b(agendar|visita|visitar|coordinar|turno|recorrer)\b", "scheduling"),
    (r"\b(fotos?|im[aá]genes?|ver fotos?|mostr[aá] fotos?)\b", "photos"),
    (r"\b(detalles?|info|informaci[oó]n|mostrame m[aá]s|ver m[aá]s)\b", "detalles"),
    (r"\b(comparar|comparativa|diferencia entre|cu[aá]l es mejor)\b", "comparing"),
]


def _parse_budget(text: str) -> float | None:
    """Extract a budget amount from text. Returns None if no budget found."""
    m = BUDGET_PATTERN.search(text.lower())
    if not m:
        return None

    raw = m.group(1).strip().replace(",", "").replace(".", "")
    multipliers = {
        "mil": 1_000, "k": 1_000, "lucas": 1_000,
        "millones": 1_000_000, "millón": 1_000_000, "palos": 1_000_000,
    }

    # Handle attached multiplier: "100mil" → base=100, mult=1000
    for suffix, mult in multipliers.items():
        if raw.endswith(suffix):
            try:
                base = float(raw[:-len(suffix)])
                return base * mult
            except ValueError:
                pass

    # Space-separated: "100 mil"
    parts = raw.split()
    try:
        base = float(parts[0])
        if len(parts) > 1 and parts[1] in multipliers:
            return base * multipliers[parts[1]]
        return base
    except (ValueError, IndexError):
        return None


def _parse_bedrooms(text: str) -> int | None:
    """Extract minimum bedrooms from text."""
    m = BEDROOMS_PATTERN.search(text.lower())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _fuzzy_normalize(text: str) -> str:
    """Normalize common typos and merged words for regex matching.

    Handles:
    - Merged "para" + operation: "paraalquilar" -> "para alquilar"
    - Transposed letters: aql -> alq ("aqluilar" -> "alquilar")
    - Common letter swaps: "alqruilar" -> "alquilar"
    - Specific known typos: "departamneto" -> "departamento"
    - Standalone misspelled operations: "aqluirar" -> "alquilar"
    """
    # Fix merged "para" + operation: "paraalquilar" -> "para alquilar"
    text = re.sub(
        r"\bpara(alquilar|alquiler|alqilar|aqluilar|alqruilar|aqluirar|alquirlar|alqruiler|alqruirar|alqilar)\b",
        r"para \1",
        text,
    )

    # Fix transposed letters: aql -> alq  (e.g., "aqluilar" -> "alquilar")
    text = text.replace("aql", "alq")

    # Fix common letter transpositions in "alquilar"/"alquiler"
    # "alqruilar" -> "alquilar", "alqruiler" -> "alquiler"
    text = re.sub(r"alq([ru])uilar", r"alquilar", text)
    text = re.sub(r"alq([ru])uiler", r"alquiler", text)

    # Fix "alquirlar" -> "alquilar" (r and l swapped)
    text = re.sub(r"alquirlar", "alquilar", text)
    text = re.sub(r"alquirler", "alquiler", text)

    # Fix "alquirar" -> "alquilar" (e.g., "aqluirar" -> "alquirar" after aql->alq fix)
    text = re.sub(r"alquirar", "alquilar", text)
    text = re.sub(r"alquirer", "alquiler", text)

    # Fix standalone misspellings (without "para" prefix)
    # "alqruilar" alone -> "alquilar", "alqular" -> "alquilar"
    text = re.sub(r"\balq([ru])*uilar\b", "alquilar", text)
    text = re.sub(r"\balq([ru])*uiler\b", "alquiler", text)
    
    # Fix "alqilar" -> "alquilar" (missing 'u')
    text = re.sub(r"\balqilar\b", "alquilar", text)
    text = re.sub(r"\balqiler\b", "alquiler", text)

    # Fix specific known typo: "departamneto" -> "departamento"
    text = text.replace("departamneto", "departamento")

    # Fix "departamento" typo: missing second 'a' 
    text = re.sub(r"\bdepartam[e]n?to\b", "departamento", text)

    # Fix common "alq*" misspellings at word boundaries
    text = re.sub(r"\balq([ui][li]er)\b", r"alquiler", text)
    text = re.sub(r"\balq([ui][li]ar)\b", r"alquilar", text)

    return text


def update_belief(belief: ConversationBeliefState, message: str) -> ConversationBeliefState:
    """Extract entities from message and accumulate into belief state.

    Criteria are only set if not already present (first mention wins).
    Intents accumulate across turns.
    """
    text = message.lower().strip()
    fuzzy_text = _fuzzy_normalize(text)  # Typo-tolerant version for entity extraction
    belief.turn_count += 1
    belief.history.append(message)
    window = get_settings().HISTORY_WINDOW
    if len(belief.history) > window:
        belief.history = belief.history[-window:]

    # Extract operation (only if not already set)
    if belief.operation is None:
        for pattern, value in OPERATION_PATTERNS:
            if re.search(pattern, fuzzy_text):
                belief.operation = value
                break
    else:
        # User is repeating/confirming an already-set operation.
        # Only trigger a new search if no specific property is already selected.
        for pattern, _ in OPERATION_PATTERNS:
            if re.search(pattern, fuzzy_text):
                if belief.selected_property_id is None:
                    belief.active_intents.add("searching")
                break

    # Extract property type
    if belief.property_type is None:
        for pattern, value in TYPE_PATTERNS:
            if re.search(pattern, fuzzy_text):
                belief.property_type = value
                break
    else:
        # User is repeating an already-set type → reinforce search intent
        for pattern, _ in TYPE_PATTERNS:
            if re.search(pattern, fuzzy_text):
                belief.active_intents.add("searching")
                break

    # Extract zone
    if belief.zone is None:
        for pattern, value in ZONE_PATTERNS:
            if re.search(pattern, fuzzy_text):
                belief.zone = value
                break

    # Extract budget (overwrite if higher precision)
    budget = _parse_budget(fuzzy_text)
    if budget is not None:
        if belief.budget_max is None or budget > 0:
            belief.budget_max = budget

    # Extract bedrooms
    bedrooms = _parse_bedrooms(fuzzy_text)
    if bedrooms is not None and bedrooms > 0:
        if belief.bedrooms_min is None:
            belief.bedrooms_min = bedrooms

    # Extract intents (use original text to avoid false positives)
    for pattern, intent in INTENT_PATTERNS:
        if re.search(pattern, text):
            belief.active_intents.add(intent)

    # ── Extract scheduling data (and trigger scheduling intent) ────
    name_match = NAME_PATTERN.search(message)
    if name_match:
        belief.scheduling_name = name_match.group(1).strip().title()
        belief.active_intents.add("scheduling")

    phone_match = PHONE_PATTERN.search(message)
    if phone_match:
        belief.scheduling_phone = phone_match.group(1).strip()
        belief.active_intents.add("scheduling")

    day_match = DAY_PATTERN.search(message)
    if day_match:
        belief.scheduling_day = day_match.group(1).strip()
        belief.active_intents.add("scheduling")

    time_match = TIME_PATTERN.search(message)
    if time_match:
        belief.scheduling_time = time_match.group(1).strip()
        belief.active_intents.add("scheduling")

    # Detect property reference by description (not ID)
    ref_match = re.search(
        r"\b(el|la|ese|esa|aquel|aquella)\s+(monoambiente|departamento|depto|depa|casa|ph|terreno|primero|primera|segundo|segunda|tercero|tercera|m[aá]s barato|m[aá]s caro|m[aá]s grande|m[aá]s chico)\b",
        fuzzy_text,
    )
    if ref_match:
        belief.active_intents.add("referencing_property")

    # Extract selected property ID from patterns like "el 3", "depto 5", "ID 7"
    id_match = re.search(r"\b(?:id|nro|número|nº|numero|el|la|propiedad)\s*#?\s*(\d+)\b", fuzzy_text)
    if id_match:
        try:
            belief.selected_property_id = int(id_match.group(1))
        except ValueError:
            pass

    # Ordinal resolution: "primero", "segundo", "tercero" → resolve from last_search_ids
    ordinal_match = re.search(
        r"\b(primero|primera|primer|segundo|segunda|tercero|tercera|cuarto|cuarta|"
        r"quinto|quinta|[uú]ltimo|[uú]ltima|anteultimo|ante[uú]ltimo)\b", fuzzy_text
    )
    if ordinal_match and belief.last_search_ids:
        ordinal_map = {
            "primero": 0, "primera": 0, "primer": 0,
            "segundo": 1, "segunda": 1,
            "tercero": 2, "tercera": 2,
            "cuarto": 3, "cuarta": 3,
            "quinto": 4, "quinta": 4,
        }
        word = ordinal_match.group(1).lower().replace("ú", "u")
        if word in ("ultimo", "ultima"):
            idx = len(belief.last_search_ids) - 1
        elif word in ("anteultimo",):
            idx = len(belief.last_search_ids) - 2
        else:
            idx = ordinal_map.get(word, 0)
        if 0 <= idx < len(belief.last_search_ids):
            resolved_id = belief.last_search_ids[idx]
            belief.selected_property_id = resolved_id
            belief.active_intents.add("ordinal_reference")

    # ── Reconcile property_type when user selects a property from search results ──
    # If the user picks a property by ID that came from the last search,
    # property_type may be stale (e.g. searched "departamento", got casas, picked [44]).
    # Align property_type to the actual property so the directive engine doesn't re-search.
    if (belief.selected_property_id is not None
            and belief.selected_property_id in (belief.last_search_ids or [])):
        actual_type = _property_type_from_context(
            belief.last_search_context or "", belief.selected_property_id
        )
        if actual_type is not None:
            belief.property_type = actual_type
        else:
            # Type unparseable → clear to prevent stale-type re-search
            belief.property_type = None
        # Selecting a concrete property is NOT a new-search signal
        belief.active_intents.discard("searching")

    # ⏱️ Update timestamp for session staleness detection
    belief.last_updated_at = time.time()

    return belief
