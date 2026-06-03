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


# Maps a referenced word from "la casa" / "el depto" to a canonical type.
_REF_TYPE_SYNONYMS = {
    "monoambiente": "departamento",
    "departamento": "departamento",
    "depto": "departamento",
    "depa": "departamento",
    "casa": "casa",
    "ph": "ph",
    "terreno": "terreno",
    "lote": "terreno",
}


def _resolve_property_by_type(belief, ref_word: str) -> "int | None":
    """Resolve a type-based reference ("la casa") to a property ID.

    Returns the ID only when resolution is unambiguous (exactly one match).
    """
    ids = belief.last_search_ids or []
    if len(ids) == 1:
        return ids[0]

    target_type = _REF_TYPE_SYNONYMS.get((ref_word or "").strip().lower())
    if not target_type:
        return None

    context = belief.last_search_context or ""
    if not context:
        return None

    matches: list = []
    for pid in ids:
        ctx_type = _property_type_from_context(context, pid)
        if ctx_type == target_type:
            matches.append(pid)

    if len(matches) == 1:
        return matches[0]
    return None


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

# ── "Don't care about X" broadening patterns ─────────────────
# Each pattern detects that the user explicitly doesn't want to filter by a
# criterion. Matching adds the criterion name to belief.criteria_any so the
# narrowing loop skips it. Reversed when the user later provides a concrete value.

# Zone: "cualquier zona", "no importa el barrio", "donde sea", etc.
_ZONE_BROADEN = re.compile(
    r"\b(cualquier(?:a)?\s+(?:otra\s+)?(?:zona|barrio|lado|lugar|parte)|"
    r"otra\s+zona|otras?\s+zonas?|todas?\s+las\s+zonas?|"
    r"no\s+importa\s+(?:la\s+)?(?:zona|el\s+barrio)|sin\s+importar\s+(?:la\s+)?zona|"
    r"en\s+cualquier\s+(?:lado|lugar|parte)|donde\s+sea)\b",
    re.IGNORECASE,
)

# Bedrooms: "no importa cuántos dormitorios", "cualquier cantidad", etc.
_BEDROOMS_BROADEN = re.compile(
    r"\b(no\s+importa\s+(?:cu[aá]ntos?|los?|la\s+cantidad\s+de)?\s*"
    r"(?:dormitorios?|habitaciones?|ambientes?|cuartos?)|"
    r"cualquier(?:a)?\s+(?:cantidad|n[uú]mero)\s+de\s+"
    r"(?:dormitorios?|habitaciones?|ambientes?)|"
    r"sin\s+importar\s+(?:l[ao]s?\s+)?(?:dormitorios?|habitaciones?)|"
    r"(?:dormitorios?|habitaciones?|ambientes?)\s+(?:da|me\s+da)\s+(?:lo\s+)?igual|"
    r"(?:da|me\s+da)\s+(?:lo\s+)?igual\s+(?:los?\s+)?(?:dormitorios?|habitaciones?))\b",
    re.IGNORECASE,
)

# Budget: "sin límite de presupuesto", "no importa el precio", etc.
_BUDGET_BROADEN = re.compile(
    r"\b(sin\s+l[ií]mite\s+(?:de\s+)?(?:presupuesto|precio|plata)|"
    r"no\s+(?:tengo\s+)?l[ií]mite\s+(?:de\s+)?(?:presupuesto|plata)|"
    r"no\s+importa\s+(?:el\s+)?(?:precio|presupuesto|valor|costo)|"
    r"(?:el\s+)?precio\s+no\s+(?:me\s+)?importa|"
    r"cualquier(?:a)?\s+(?:precio|presupuesto|valor)|"
    r"presupuesto\s+abierto|"
    r"(?:precio|presupuesto)\s+(?:da|me\s+da)\s+(?:lo\s+)?igual)\b",
    re.IGNORECASE,
)

# Property type: "cualquier tipo de propiedad", "da lo mismo el tipo", etc.
_TYPE_BROADEN = re.compile(
    r"\b(cualquier(?:a)?\s+(?:tipo|clase)\s+(?:de\s+)?(?:propiedad|inmueble)|"
    r"no\s+importa\s+(?:el\s+)?(?:tipo|clase)\s+(?:de\s+)?(?:propiedad|inmueble)|"
    r"(?:tipo|clase)\s+(?:da|me\s+da)\s+(?:lo\s+)?igual|"
    r"cualquier\s+(?:propiedad|inmueble))\b",
    re.IGNORECASE,
)

# Operation: "me da igual alquilar o comprar", "no importa si es alquiler o venta", etc.
_OPERATION_BROADEN = re.compile(
    r"\b((?:me\s+)?da\s+(?:lo\s+)?igual\s+(?:si\s+)?(?:alquil|compr)|"
    r"no\s+importa\s+si\s+(?:es\s+)?(?:alquiler|venta|alquilar|comprar)|"
    r"(?:alquil|compr)(?:ar|er|o)\s+o\s+(?:compr|alquil)(?:ar|er|o)\s+"
    r"(?:me\s+)?da\s+(?:lo\s+)?igual)\b",
    re.IGNORECASE,
)

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
    # Time-of-day words require a preposition ("a la tarde", "por la mañana").
    # Bare "mañana/tarde/noche" is NOT matched here — it collided with greetings
    # ("buenas tardes") and idioms ("se hace tarde", "más tarde"), seeding a false
    # scheduling_time. "mediodía" stays (unambiguous).
    r"|mediod[ií]a"
    r"|(?:a|de|por|en)\s+la\s+(?:ma[nñ]ana|tarde|noche))",
    re.IGNORECASE,
)

INTENT_PATTERNS = [
    (r"\b(busco|quiero|necesito|buscando|estoy buscando|me interesa)\b", "searching"),
    (r"\b(?:cu[aá]ndo|cuando)\s+(?:puedo|podemos|podr[ií]a|podria)\s+(?:ir|pasar|caer|ver|visitar|conocer)\b", "scheduling"),
    (r"\b(?:quiero|quisiera|me\s+gustar[ií]a)\s+(?:ir|pasar|ver|visitar|conocer|coordinar)\b", "scheduling"),
    (r"\b(agendar|visita|visitar|coordinar|turno|recorrer)\b", "scheduling"),
    (r"\b(fotos?|im[aá]genes?|ver fotos?|mostr[aá] fotos?)\b", "photos"),
    (r"\b(detalles?|info|informaci[oó]n|mostrame m[aá]s|ver m[aá]s)\b", "detalles"),
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

    # ── Operation: broadening check FIRST, then explicit override ──
    _ca = getattr(belief, "criteria_any", None)  # shorthand; may be None on old sessions
    if _OPERATION_BROADEN.search(text):
        belief.operation = None
        if _ca is not None:
            _ca.add("operation")
    else:
        _new_op = None
        for pattern, value in OPERATION_PATTERNS:
            if re.search(pattern, fuzzy_text):
                _new_op = value
                break
        if _new_op is not None:
            if _ca is not None:
                _ca.discard("operation")
            if belief.operation is not None and _new_op != belief.operation:
                belief.operation = _new_op  # explicit switch
                if belief.selected_property_id is None:
                    belief.active_intents.add("searching")
            elif belief.operation is None:
                belief.operation = _new_op
            elif belief.selected_property_id is None:
                belief.active_intents.add("searching")  # repeat/confirm

    # ── Property type: broadening check FIRST, then explicit override ──
    if _TYPE_BROADEN.search(text):
        belief.property_type = None
        if _ca is not None:
            _ca.add("property_type")
    else:
        _new_type = None
        for pattern, value in TYPE_PATTERNS:
            if re.search(pattern, fuzzy_text):
                _new_type = value
                break
        if _new_type is not None:
            if _ca is not None:
                _ca.discard("property_type")
            if belief.property_type is not None and _new_type != belief.property_type:
                belief.property_type = _new_type
                belief.zone = None  # type switch → drop the (now-irrelevant) zone
                # Type switch is NOT an explicit "any zone" preference — clear criteria_any
                # so the narrowing loop can ask for zone again for the new property type.
                if _ca is not None:
                    _ca.discard("zone")
                belief.active_intents.add("searching")
            elif belief.property_type is None:
                belief.property_type = _new_type
            else:
                belief.active_intents.add("searching")  # repeat/confirm

    # ── Zone: broadening clears it; explicit mention OVERRIDES ──
    if _ZONE_BROADEN.search(text):
        belief.zone = None
        if _ca is not None:
            _ca.add("zone")
        if belief.selected_property_id is None:
            belief.active_intents.add("searching")
    else:
        for pattern, value in ZONE_PATTERNS:
            if re.search(pattern, fuzzy_text):
                belief.zone = value  # override
                if _ca is not None:
                    _ca.discard("zone")
                break

    # ── Budget: broadening check FIRST, then explicit value ──
    if _BUDGET_BROADEN.search(text):
        belief.budget_max = None
        if _ca is not None:
            _ca.add("budget_max")
    else:
        budget = _parse_budget(fuzzy_text)
        if budget is not None:
            if _ca is not None:
                _ca.discard("budget_max")
            if belief.budget_max is None or budget > 0:
                belief.budget_max = budget

    # ── Bedrooms: broadening check FIRST, then explicit value ──
    if _BEDROOMS_BROADEN.search(text):
        belief.bedrooms_min = None
        if _ca is not None:
            _ca.add("bedrooms_min")
    else:
        bedrooms = _parse_bedrooms(fuzzy_text)
        if bedrooms is not None and bedrooms > 0:
            if _ca is not None:
                _ca.discard("bedrooms_min")
            belief.bedrooms_min = bedrooms

    # Extract intents (use original text to avoid false positives)
    for pattern, intent in INTENT_PATTERNS:
        if re.search(pattern, text):
            belief.active_intents.add(intent)

    # ── Extract scheduling data ONLY inside an active scheduling context ──
    # A bare temporal token must NEVER *create* the scheduling intent. Otherwise a
    # greeting ("buenas tardes") or a fresh search ("busco depto a la tarde") would
    # set scheduling_time and flip on the scheduling flow, which then hijacks the
    # next turn ("¿qué día querés coordinar?") instead of searching.
    #
    # The scheduling intent is established BEFORE this block by:
    #   - INTENT_PATTERNS above (agendar / visita / coordinar / "quiero ir a ver"), or
    #   - an active `awaiting=scheduling_*` slot (the booking flow already in progress).
    # When neither holds, we do not touch scheduling state — the LLM specialist drives
    # the conversation from the real message instead of a regex-seeded slot.
    _awaiting = str(getattr(belief, "awaiting", "") or "")
    _scheduling_active = (
        "scheduling" in belief.active_intents
        or _awaiting.startswith("scheduling")
    )
    if _scheduling_active:
        name_match = NAME_PATTERN.search(message)
        if name_match:
            belief.scheduling_name = name_match.group(1).strip().title()

        phone_match = PHONE_PATTERN.search(message)
        if phone_match:
            belief.scheduling_phone = phone_match.group(1).strip()

        day_match = DAY_PATTERN.search(message)
        if day_match:
            belief.scheduling_day = day_match.group(1).strip()

        time_match = TIME_PATTERN.search(message)
        if time_match:
            belief.scheduling_time = time_match.group(1).strip()

    # Detect property reference by description (not ID)
    ref_match = re.search(
        r"\b(el|la|ese|esa|aquel|aquella)\s+(monoambiente|departamento|depto|depa|casa|ph|terreno|primero|primera|segundo|segunda|tercero|tercera|m[aá]s barato|m[aá]s caro|m[aá]s grande|m[aá]s chico)\b",
        fuzzy_text,
    )
    if ref_match:
        belief.active_intents.add("referencing_property")
        # Resolve a type-based reference ("la casa", "el depto") to a concrete ID.
        if belief.selected_property_id is None:
            resolved = _resolve_property_by_type(belief, ref_match.group(2))
            if resolved is not None:
                belief.selected_property_id = resolved
                belief.active_intents.add("resolved_by_description")

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


# ── LLM fallback for the scheduling_name slot (schema v4) ──────────
# Anaphoric replies like "al mío" must NOT be silently turned into the
# WhatsApp display name. Return a signal so the bot re-asks the name.

_NAME_ANAPHORA = re.compile(
    r"\b(al?\s+m[ií]o|a\s+mi\s+nombre|el\s+m[ií]o|con\s+mi\s+nombre|mi\s+nombre|para\s+m[ií])\b",
    re.IGNORECASE,
)

# Returned by extract_scheduling_name_llm to signal: re-ask the name concretely.
NAME_REASK_SIGNAL = "__REASK_NAME__"


async def extract_scheduling_name_llm(
    belief, message: str
) -> "str | None":
    """Extract a full name when the bot is awaiting scheduling_name.

    Returns:
      - a name string       → caller sets belief.scheduling_name
      - NAME_REASK_SIGNAL   → user gave anaphora ("al mío") with no name; re-ask
      - None                → nothing extractable; caller keeps awaiting and re-anchors
    """
    # 1. Anaphora guard FIRST — "al mío" must never become a real name.
    if _NAME_ANAPHORA.search(message) and not NAME_PATTERN.search(message):
        return NAME_REASK_SIGNAL

    # 2. Regex marker form ("me llamo X", "soy X") — recheck here.
    m = NAME_PATTERN.search(message)
    if m:
        return m.group(1).strip().title()

    # 3. LLM extractor (reuse the hybrid name extractor).
    try:
        from app.core.hybrid.name import name_extractor
        ctx = {
            "awaiting": "scheduling_name",
            "last_bot_message": getattr(belief, "last_bot_message", ""),
        }
        result = await name_extractor.parse(message, ctx)
        if result.value:
            return str(result.value).strip().title()
    except Exception:
        pass

    # 4. Bare token(s) that look like a name → accept as-is.
    stripped = message.strip()
    if (1 <= len(stripped.split()) <= 4
            and re.fullmatch(r"[A-Za-záéíóúüñÁÉÍÓÚÜÑ\s]+", stripped)
            and not _NAME_ANAPHORA.search(stripped)):
        return stripped.title()

    return None


# ── Day / time slot extractors ─────────────────────────────────────────────────
_DAY_PHRASE = re.compile(
    r"\b("
    r"(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)"
    r"(?:\s+que\s+viene|\s+pr[óo]ximo)?"
    r"|pasado\s+ma[ñn]ana"
    r"|ma[ñn]ana"
    r"|hoy"
    r")\b",
    re.IGNORECASE,
)


def extract_scheduling_day(message: str) -> "str | None":
    """Extract a concrete day phrase from the user's message.

    Returns the day phrase (e.g. 'viernes', 'viernes que viene', 'mañana')
    to be stored as belief.scheduling_day, or None if no concrete day found.
    """
    if not message:
        return None
    m = _DAY_PHRASE.search(message)
    if not m:
        return None
    return m.group(1).strip().lower()


def extract_scheduling_time(message: str) -> "str | None":
    """Extract a concrete clock time from the user's message.

    Returns a 'HH:MM' string (e.g. '10:00', '15:00') to be stored as
    belief.scheduling_time, or None if no concrete time found.
    """
    if not message:
        return None
    try:
        from app.utils.date_parser import _extract_time_from_text
        parsed = _extract_time_from_text(message)
    except Exception:
        return None
    if not parsed or parsed[0] is None:
        return None
    hour = parsed[0]
    minute = parsed[1] if len(parsed) > 1 else 0
    return f"{int(hour):02d}:{int(minute or 0):02d}"
