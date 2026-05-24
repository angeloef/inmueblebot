"""
Router de capacidades y etapas del agente inmobiliario.

Determina:
- Etapa de conversación (dónde estamos)
- Capacidad requerida (qué podemos hacer)
- Si el mensaje está fuera de alcance
- Si se debe hacer handoff por límite de reintentos

Regex-first, LLM-fallback para casos ambiguos. Rápido, determinista.
"""

import re
from typing import Optional, List
from loguru import logger

# ── Etapas de conversación ─────────────────────────────────────────────────────

STAGE_GREETING        = "SALUDO_INICIAL"
STAGE_SEARCH          = "BUSQUEDA"
STAGE_DETAIL          = "DETALLE_PROPIEDAD"
STAGE_PHOTOS          = "FOTOS"               # v3.0: user explicitly asks for photos
STAGE_COMPARE         = "COMPARAR"            # v3.0: user asks to compare properties
STAGE_SCHEDULING      = "AGENDANDO"
STAGE_APPOINTMENT     = "GESTION_TURNOS"
STAGE_FAQ             = "CONSULTA"
STAGE_GENERAL         = "CONVERSACION_GENERAL"
STAGE_OUT_OF_SCOPE    = "OUT_OF_SCOPE"
STAGE_HANDOFF         = "HANDOFF_REQUIRED"


# ── v3.0: LLM FAQ classifier (regex-first, LLM-fallback) ────────────────────

_FAQ_CLASSIFIER_MESSAGES = [
    {
        "role": "system",
        "content": (
            "Sos un clasificador de intencion. Responde SOLO con 'FAQ' o 'NO'.\\n"
            "Responde 'FAQ' si el mensaje es una pregunta sobre el funcionamiento "
            "de una inmobiliaria, el proceso de alquilar/comprar, requisitos, "
            "documentacion, garantias, formas de pago, horarios, comisiones, o "
            "cualquier tema operativo de una inmobiliaria.\\n"
            "Responde 'NO' si el mensaje busca propiedades, agenda visitas, "
            "gestiona turnos, o cualquier cosa que no sea una consulta informativa."
        ),
    },
]


async def is_likely_faq(message: str) -> bool:
    """Quick LLM check: is this message an FAQ question about real estate?
    
    Used as fallback when regex can't determine if a message is FAQ or search.
    Returns False on any error (graceful degradation to regex-only behavior).
    """
    try:
        from app.agents.llm_router import llm_router
        msgs = list(_FAQ_CLASSIFIER_MESSAGES)
        msgs.append({"role": "user", "content": message[:300]})
        resp = await llm_router.ainvoke(
            messages=msgs,
            tools=None,
            temperature=0,
            max_tokens=5,
        )
        result = (resp.content or "").strip().upper()
        return "FAQ" in result
    except Exception as e:
        logger.warning(f"[Router] FAQ classifier failed: {e}")
        return False


async def is_legitimate_real_estate(message: str) -> bool:
    """Quick LLM check: is this a legitimate real estate question that the
    regex incorrectly flagged as out-of-scope?
    
    Used to override out-of-scope false positives (e.g., 'que opinas de la
    escritura?' sounds like opinion but is actually about property title).
    """
    try:
        from app.agents.llm_router import llm_router
        msgs = [
            {
                "role": "system",
                "content": (
                    "Sos un clasificador. Responde SOLO 'SI' o 'NO'.\\n"
                    "Responde 'SI' si el mensaje es una consulta legitima sobre "
                    "el negocio inmobiliario (alquiler, compra, propiedades, "
                    "visitas, tramites, precios, financiacion, etc.).\\n"
                    "Responde 'NO' SOLO si el mensaje es claramente de otro rubro "
                    "(recetas, medicina, tecnologia, deportes, clima, etc.)."
                ),
            },
            {"role": "user", "content": message[:300]},
        ]
        resp = await llm_router.ainvoke(
            messages=msgs,
            tools=None,
            temperature=0,
            max_tokens=5,
        )
        result = (resp.content or "").strip().upper()
        return "SI" in result
    except Exception as e:
        logger.warning(f"[Router] Out-of-scope override failed: {e}")
        return False

# ── Capacidades del bot ───────────────────────────────────────────────────────

CAP_SEARCH    = "search"
CAP_DETAIL    = "detail"
CAP_SCHEDULE  = "schedule"
CAP_APPOINT   = "manage_appointment"
CAP_FAQ       = "faq"
CAP_CONTACT   = "contact"

ALL_CAPABILITIES = [CAP_SEARCH, CAP_DETAIL, CAP_SCHEDULE, CAP_APPOINT, CAP_FAQ, CAP_CONTACT]

FAIL_THRESHOLD = 2  # Intentos fallidos por capacidad antes de handoff


async def detect_stage(
    message: str,
    context: dict,
    history: Optional[List[dict]] = None,
    current_state: Optional[str] = None,
) -> str:
    """
    Detecta la etapa actual de la conversación usando flags de estado + keywords.

    Args:
        message: Mensaje del usuario
        context: Contexto combinado del usuario (merged_context)
        history: Historial de mensajes recientes
        current_state: Estado actual del state machine (para follow-up detection)

    Returns:
        str: Una de las constantes STAGE_*
    """
    msg_lower = message.lower().strip()
    is_new_session = not history or len(history) < 2

    # 1. Handoff por límite de reintentos
    for cap in ALL_CAPABILITIES:
        fail_key = f"{cap}_fail_count"
        if context.get(fail_key, 0) >= FAIL_THRESHOLD:
            return STAGE_HANDOFF

    # 2. Fuera de alcance (se verifica temprano)
    if is_out_of_scope(message):
        # v3.0: LLM override — legitimate real estate questions that
        # the regex incorrectly flagged (e.g., 'que opinas de la escritura?'
        # contains 'opinás' but is actually about property titles)
        if await is_legitimate_real_estate(message):
            logger.info(f"[Router] Out-of-scope overridden by LLM: '{message[:80]}'")
            # Don't return — fall through to FAQ/search detection below
        else:
            return STAGE_OUT_OF_SCOPE

    # 3. Saludo inicial — solo si el primer mensaje ES realmente un saludo
    GREETING_KW = ["hola", "buenas", "buen día", "buen dia", "buenas tardes",
                   "buenas noches", "buenos días", "buenos dias", "qué tal",
                   "que tal", "hello", "hi", "hey", "saludos"]
    _is_just_greeting = is_new_session and not any(
        kw in msg_lower for kw in [
            # Search keywords
            "busco", "buscando", "quiero", "necesito", "hay", "tienen",
            "alquilar", "alquiler", "comprar", "compra", "venta",
            "departamento", "casa", "terreno",
            "propiedad", "inmueble",
            "presupuesto", "precio",
            # Appointment keywords
            "reprogramar", "cancelar", "mis citas",
            # FAQ keywords
            "horario", "dirección", "teléfono",
            # Scheduling kewords
            "visita", "agendar",
        ]
    ) and any(kw in msg_lower for kw in GREETING_KW)
    if _is_just_greeting:
        return STAGE_GREETING

    # 4. Gestión de turnos (reschedule/cancel) — palabras clave fuertes
    if any(kw in msg_lower for kw in [
        "reprogramar", "cancelar", "cambiar la cita", "cambiar el horario",
        "modificar la visita", "no puedo ir", "no voy a poder",
        "cancelar mi", "mover la cita", "reagendar",
    ]):
        return STAGE_APPOINTMENT

    # 5. Agendando — el flag pending_scheduling está activo O keywords de scheduling
    pending = context.get("pending_scheduling_info")
    if pending and isinstance(pending, dict) and pending.get("active"):
        return STAGE_SCHEDULING

    # 5b. Agendando — keywords explícitos (ANTES de search para evitar falsos positivos)
    if any(kw in msg_lower for kw in [
        "agendar", "agendame", "agendá", "coordinar visita",
        "reservar turno", "reservar cita", "pedir turno",
        "ir a ver", "conocer la propiedad", "visitarla",
        "quiero verla", "cuándo puedo ir", "cuando puedo ir",
        "a partir de cuando", "desde cuando", "puedo alquilar",
        "cuando puedo", "está disponible", "está libre",
        "fecha de entrada", "puedo visitar", "disponible para",
    ]):
        return STAGE_SCHEDULING

    # 6. FAQ / consulta sobre la inmobiliaria
    if any(kw in msg_lower for kw in [
        "horario", "dirección", "teléfono", "tel", "mail", "email",
        "cómo funcionan", "comisión", "honorarios", "cómo trabajan",
        "dónde están", "whatsapp", "contacto", "atención",
        "abren", "cierran", "días de atención", "dias de atencion",
    ]):
        return STAGE_FAQ

    # 6b. v3.0: LLM FAQ fallback — catches questions like
    # "como serie el tema para ingresar a alquilar?" that don't match keywords
    _question_patterns = ["?", "como ", "cómo ", "que ", "qué ", "cual ", "cuál ",
                          "cuando ", "cuándo ", "donde ", "dónde ", "cuanto ",
                          "cuánto ", "quien ", "quién ", "cuales ", "cuáles ",
                          "seria ", "sería "]
    if any(msg_lower.startswith(p) or p in msg_lower for p in _question_patterns):
        if await is_likely_faq(message):
            logger.info(f"[Router] FAQ detected by LLM: '{message[:80]}'")
            return STAGE_FAQ

    # 7. Detalle de propiedad (check BEFORE search when active property exists)
    active_prop = context.get("selected_property_id") or context.get("active_property_id")
    if active_prop:
        # 7a. Explicit photo request (check first — most specific)
        photo_kw = ["foto", "fotos", "imagen", "imágenes", "imagenes", "ver foto",
                     "mostrar foto", "mira", "mírame"]
        if any(kw in msg_lower for kw in photo_kw):
            return STAGE_PHOTOS
        
        # 7b. Compare request
        compare_kw = ["comparar", "comparame", "diferencia entre", "cual es mejor",
                       "cuál es mejor", "comparación", "comparacion"]
        if any(kw in msg_lower for kw in compare_kw):
            return STAGE_COMPARE
        
        # 7c. Generic detail/info request
        detail_kw = ["ese", "esa", "eso", "detalle",
                      "saber más", "saber mas", "información", "informacion",
                      "cuánto", "cuanto", "precio", "más info", "mas info",
                      "decime", "contame", "mostrame", "ver"]
        if any(kw in msg_lower for kw in detail_kw):
            return STAGE_DETAIL

    # 8. Búsqueda de propiedades
    search_kw = [
        "busco", "quiero", "necesito", "mostrame", "mostrar",
        "hay", "tienen", "alquiler", "compra", "alquilar", "comprar",
        "departamento", "casa", "terreno", "ph", "local",
        "propiedad", "propiedades", "inmueble", "inmuebles",
        "presupuesto", "hasta", "desde", "precio",
        "zona", "barrio", "ubicación", "ubicacion", "centro", "cerca",
        "dormitorio", "ambientes", "baños", "cochera",
        "opciones", "alternativas", "catálogo", "catalogo", "listado",
    ]
    if any(kw in msg_lower for kw in search_kw):
        return STAGE_SEARCH

    # 9. Contacto (agente, teléfono, etc.)
    if any(kw in msg_lower for kw in [
        "asesor", "agente", "contacto", "hablar con",
        "número", "numero", "whatsapp", "llamar",
    ]):
        return STAGE_FAQ  # Reutiliza FAQ stage, contact_info se maneja por tools

    # 10. Searching-state follow-up: user is refining/continuing a search
    #    e.g. "y cerca del centro?", "mejor en Palermo", "con cochera"
    _searching_states = {"searching", "viewing_detail", "viewing_photos",
                          "viewing_compare"}
    if current_state and current_state in _searching_states:
        _refinement_kw = [
            "centro", "cerca", "zona", "barrio", "ubicación", "ubicacion",
            "alrededor", "alrededores", "por", "mejor en", "que tal",
            "cómo es", "como es", "y ", "con ", "sin ",
        ]
        # Short follow-up message that mentions location-like terms
        if len(msg_lower) < 100 and any(kw in msg_lower for kw in _refinement_kw):
            return STAGE_SEARCH

    # 11. Fallback
    return STAGE_GENERAL


def detect_capability(message: str, context: dict) -> Optional[str]:
    """
    Detecta qué capacidad del bot se necesita para responder al mensaje.

    Returns:
        str: Una de las constantes CAP_*, o None si no hay capacidad que coincida.
    """
    msg_lower = message.lower().strip()

    # Appointment management
    if any(kw in msg_lower for kw in [
        "reprogramar", "cancelar cita", "cancelar visita",
        "cambiar la cita", "mis citas", "mis visitas",
        "mis turnos", "mis agendamientos",
    ]):
        return CAP_APPOINT

    # Schedule a visit
    if any(kw in msg_lower for kw in [
        "agendar", "visita", "coordinar", "turno", "cita",
        "ir a ver", "conocer", "puedo ir", "visitarla",
        "quiero verla", "agendá", "agendame",
    ]):
        return CAP_SCHEDULE

    # Property detail (check before search for 'mostrame', 'foto', etc.)
    if any(kw in msg_lower for kw in [
        "foto", "fotos", "imagen", "detalle",
        "saber más", "más información", "información",
        "cuánto sale", "cuanto sale", "cuál es el precio",
        "decime de esa", "contame de esa",
    ]):
        return CAP_DETAIL

    # Property search
    if any(kw in msg_lower for kw in [
        "busco", "quiero", "necesito", "hay", "tienen",
        "departamento", "casa", "terreno", "ph", "local",
        "alquiler", "compra", "alquilar", "comprar",
        "propiedad", "inmueble", "zona", "barrio",
        "opciones", "alternativas", "mostrame",
        "presupuesto", "hasta", "desde",
    ]):
        return CAP_SEARCH

    # FAQ
    if any(kw in msg_lower for kw in [
        "horario", "dirección", "teléfono", "mail",
        "cómo funciona", "comisión", "honorarios",
        "dónde están", "consulta", "pregunta",
    ]):
        return CAP_FAQ

    # Contact
    if any(kw in msg_lower for kw in [
        "asesor", "agente", "contacto", "número",
        "whatsapp", "llamar", "hablar con alguien",
    ]):
        return CAP_CONTACT

    # No capability matched
    return None


def is_out_of_scope(message: str) -> bool:
    """
    Detecta si el mensaje está fuera del alcance del bot.

    Returns:
        bool: True si el bot NO debería intentar responder.
    """
    msg_lower = message.lower().strip()

    patterns = [
        # Price negotiations / appraisals
        r"cu[aá]nto (vale|sale|cuesta|sale)\s*(una|un|la|el|mi|mis)?\s*(casa|depto|propiedad|terreno)",
        r"mejor (oferta|precio|propuesta)",
        r"negoci[oó]r",
        r"pod[eé]s (bajar|re[bv]ajar|hacer descuento)",

        # Legal / financial
        r"(contrato|escriban[ií]a|impuesto|escritura|titulo|título|boleto|hipoteca)",
        r"(sucesión|sucesion|herederos|división|divisor)",
        r"(cr[eé]dito|cr[eé]dito hipotecario|pr[eé]stamo|uva|uvas)",

        # Opinions / subjective
        r"qu[eé] (opinión|opin[áa]s|pens[aá]s|cre[eé]s|te parece|me recomen[d]?[aá]s)",
        r"es (bueno|mala|confiable|seguro)\s+(invertir|comprar|alquilar)",
        r"te (parece|parecen)",

        # Completely off-topic
        r"(receta|c[óo]digo|chiste|traducci[óo]n|tarea|consejo\s+de\s+salud)",
        r"(clima|clima|temperatura|lluvia|pronóstico)",
        r"(noticia|política|política|f[úu]tbol|deporte)",
        r"(película|pelicula|serie|m[uú]sica|canción|cancion|libro)",
        r"c[óo]mo (programar|hacer una págin)",
        r"(javascript|código|codigo|html|css)",

        # Comparisons with other brokerages
        r"otr[oa]\s+(inmobiliaria|agenci|corredor)",
        r"(mejor|peor)\s+que\s+(otr[oa]|la competencia)",
        r"((zonaprop|mercadolibre|argenprop|properati)\b)",
    ]

    return any(re.search(p, msg_lower, re.IGNORECASE) for p in patterns)


def get_fail_count(context: dict, capability: str) -> int:
    """Obtiene el contador de fallos para una capacidad."""
    return context.get(f"{capability}_fail_count", 0)


def increment_fail_count(context: dict, capability: str) -> dict:
    """Incrementa el contador de fallos para una capacidad y devuelve el context actualizado."""
    key = f"{capability}_fail_count"
    context[key] = context.get(key, 0) + 1
    return context


def reset_fail_count(context: dict, capability: str) -> dict:
    """Resetea el contador de fallos para una capacidad."""
    key = f"{capability}_fail_count"
    if key in context:
        del context[key]
    return context


def should_handoff(context: dict, capability: Optional[str] = None) -> bool:
    """
    Determina si se debe hacer handoff basado en contadores de fallo.

    Args:
        context: Contexto del usuario
        capability: Capacidad específica a verificar (None = verifica todas)

    Returns:
        bool: True si alguna capacidad superó el umbral de fallos
    """
    caps = [capability] if capability else ALL_CAPABILITIES
    for cap in caps:
        if context.get(f"{cap}_fail_count", 0) >= FAIL_THRESHOLD:
            return True
    return False


# ── v2.0: Stage → State Machine state mapping ───────────────────────────────

_STAGE_TO_STATE: dict[str, str] = {
    STAGE_GREETING: "qualifying",
    STAGE_SEARCH: "searching",
    STAGE_DETAIL: "viewing_detail",
    STAGE_PHOTOS: "viewing_photos",
    STAGE_COMPARE: "viewing_compare",
    STAGE_SCHEDULING: "scheduling_ask_date",
    STAGE_APPOINTMENT: "appointment_management",
    STAGE_FAQ: "faq",
    STAGE_OUT_OF_SCOPE: "out_of_scope",
    STAGE_HANDOFF: "human_assistance",
    # STAGE_GENERAL: no mapping — defers to classifier
}


async def propose_transition(
    message: str,
    current_state: str,
    context: dict,
    history: Optional[List[dict]] = None,
) -> tuple[Optional[str], str]:
    """
    v2.0: Propone el siguiente estado basado en regex + estado actual.

    Returns:
        (proposed_state: str | None, confidence: "high" | "low")

        - (state, "high"): regex matched with high confidence, proceed immediately
        - (state, "low"): regex matched but uncertain, run classifier to confirm
        - (None, "low"): no regex match, defer to classifier
    """
    stage = await detect_stage(message, context, history, current_state)

    # ── High-confidence matches ──
    if stage == STAGE_GREETING:
        return ("qualifying", "high")

    if stage == STAGE_OUT_OF_SCOPE:
        return ("out_of_scope", "high")

    if stage == STAGE_HANDOFF:
        return ("human_assistance", "high")

    if stage == STAGE_APPOINTMENT:
        return ("appointment_management", "high")

    if stage == STAGE_FAQ:
        return ("faq", "high")

    if stage == STAGE_SEARCH:
        return ("searching", "high")

    if stage == STAGE_DETAIL:
        return ("viewing_detail", "high")

    if stage == STAGE_PHOTOS:
        return ("viewing_photos", "high")

    if stage == STAGE_COMPARE:
        return ("viewing_compare", "high")

    if stage == STAGE_SCHEDULING:
        return ("scheduling_ask_date", "high")

    # ── STAGE_GENERAL (fallback) → low confidence, defer to classifier ──
    return (None, "low")
