"""
Router de capacidades y etapas del agente inmobiliario.

Arquitectura de doble clasificador:
1. Regex ligero — detecta patrones obvios (rápido, gratuito)
2. LLM clasificador — entiende contexto y matices (preciso)
3. Tiebreaker — resuelve discrepancias entre ambos

Mantiene el safety gate (fuera de alcance) como regex determinista.
"""

import re
from typing import Optional, List
from loguru import logger

# ── Capacidades del bot ───────────────────────────────────────────────────────

CAP_SEARCH    = "search"
CAP_DETAIL    = "detail"
CAP_SCHEDULE  = "schedule"
CAP_APPOINT   = "manage_appointment"
CAP_FAQ       = "faq"
CAP_CONTACT   = "contact"

ALL_CAPABILITIES = [CAP_SEARCH, CAP_DETAIL, CAP_SCHEDULE, CAP_APPOINT, CAP_FAQ, CAP_CONTACT]

FAIL_THRESHOLD = 2  # Intentos fallidos por capacidad antes de handoff


# ── LLM Classifier ───────────────────────────────────────────────────────────

_CLASSIFIER_SYSTEM_PROMPT = (
    "Sos un clasificador de intención para un chatbot inmobiliario.\n"
    "Dado el mensaje del usuario y el contexto, respondé SOLO con el "
    "nombre del estado al que debe ir el chatbot.\n\n"
    "Estados disponibles:\n"
    "- qualifying: El usuario saluda, da información inicial, o no pidió nada específico todavía\n"
    "- searching: El usuario busca propiedades (alquilar, comprar, precios, zonas, tipos)\n"
    "- viewing_property: El usuario pregunta sobre una propiedad que ya está viendo o ya conoce\n"
    "- scheduling_ask_date: El usuario quiere agendar una visita o saber disponibilidad\n"
    "- appointment_management: El usuario quiere reprogramar o cancelar una cita existente\n"
    "- faq: El usuario pregunta sobre horarios, comisiones, políticas, documentación\n"
    "- out_of_scope: El tema NO tiene nada que ver con inmuebles\n\n"
    "Reglas:\n"
    "- 'alquilar' = searching (a menos que ya tenga propiedad activa y pregunte disponibilidad = scheduling)\n"
    "- 'cuanto sale' con propiedad activa = viewing_property, NO searching\n"
    "- 'esta amoblada' con propiedad activa = viewing_property\n"
    "- SI hay duda entre dos estados: elegí el que NO rompa el flujo actual\n"
    "- Si no hay cambio claro respecto al estado actual: repetí el estado actual exactamente\n\n"
    "Respondé SOLO con el nombre del estado, nada más."
)


async def llm_classify(message: str, current_state: str, context: dict) -> str:
    """Mini LLM call to classify message intent. Returns a state name."""
    try:
        from app.agents.llm_router import llm_router

        # Build context for the classifier
        has_property = bool(context.get("selected_property_id") or context.get("last_shown_properties"))
        has_name = bool(context.get("name") or context.get("user_name"))
        ctx_parts = [
            f"Estado actual: {current_state}",
            f"Tiene propiedad activa: {'si' if has_property else 'no'}",
        ]
        if has_name:
            ctx_parts.append(f"Nombre: {context.get('name') or context.get('user_name', '?')}")

        msgs = [
            {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Mensaje: {message[:200]}\n"
                + "\n".join(ctx_parts)
            )},
        ]
        resp = await llm_router.ainvoke(
            messages=msgs,
            tools=None,
            temperature=0,
            max_tokens=15,
        )
        result = (resp.content or "").strip().lower()
        logger.info("[Router] LLM classify: message=%r -> %s", message[:60], result)
        return result
    except Exception as e:
        logger.warning(f"[Router] LLM classify failed: {e}")
        return ""


# ── Lightweight Regex Classifier ─────────────────────────────────────────────

def light_regex_classify(message: str, current_state: str, context: dict) -> Optional[str]:
    """Minimal regex that catches only the most obvious patterns.
    Returns a state name or None (defer to LLM)."""
    msg_lower = message.lower().strip()

    # 1. Out of scope — safety gate
    if _is_out_of_scope_fast(message):
        return "out_of_scope"

    # 2. Handoff — fail threshold reached
    for cap in ALL_CAPABILITIES:
        if context.get(f"{cap}_fail_count", 0) >= FAIL_THRESHOLD:
            return "human_assistance"

    # 3. Pending scheduling flag active
    pending = context.get("pending_scheduling_info")
    if pending and isinstance(pending, dict) and pending.get("active"):
        return "scheduling_ask_date"

    # 4. Pure greeting (very first message, no other keywords)
    GREETING_KW = ["hola", "buenas", "buen día", "buenas tardes", "buenas noches",
                   "buenos días", "hello", "hi", "hey"]
    EXCLUDE_FROM_GREETING = ["quiero", "busco", "necesito", "alquilar", "comprar",
                             "departamento", "casa", "terreno", "propiedad"]
    is_new_session = context.get("is_new_session", True)
    if is_new_session and any(kw in msg_lower for kw in GREETING_KW):
        if not any(kw in msg_lower for kw in EXCLUDE_FROM_GREETING):
            return "qualifying"

    # 5. Explicit appointment management
    if any(kw in msg_lower for kw in ["reprogramar", "cancelar cita", "cancelar visita",
                                       "mis citas", "mis visitas", "mover la cita"]):
        return "appointment_management"

    # 6. Nothing obvious — defer to LLM
    return None


def _is_out_of_scope_fast(message: str) -> bool:
    """Quick out-of-scope check. Keeps the existing regex patterns."""
    msg_lower = message.lower().strip()
    patterns = [
        r"(receta|c[óo]digo|chiste|traducci[óo]n|tarea|consejo\s+de\s+salud)",
        r"(clima|temperatura|lluvia|pronóstico)",
        r"(noticia|política|f[úu]tbol|deporte)",
        r"(película|pelicula|serie|m[uú]sica|canción|cancion|libro)",
        r"c[óo]mo (programar|hacer una págin)",
        r"(javascript|código|codigo|html|css)",
    ]
    return any(re.search(p, msg_lower, re.IGNORECASE) for p in patterns)


# ── LLM Out-of-scope override ────────────────────────────────────────────────

async def is_legitimate_real_estate(message: str) -> bool:
    """Quick LLM check: is this a legitimate real estate question that the
    regex incorrectly flagged as out-of-scope?
    
    Used to override out-of-scope false positives.
    """
    try:
        from app.agents.llm_router import llm_router
        msgs = [
            {
                "role": "system",
                "content": (
                    "Sos un clasificador. Responde SOLO 'SI' o 'NO'.\n"
                    "Responde 'SI' si el mensaje es una consulta legitima sobre "
                    "el negocio inmobiliario (alquiler, compra, propiedades, "
                    "visitas, tramites, precios, financiacion, etc.).\n"
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


# ── Legacy out-of-scope (kept for backward compat with webhook.py) ───────────

# We keep the full is_out_of_scope for places that import it directly
# (webhook.py and any external callers). The fast version above is for
# internal use only.

_OUT_OF_SCOPE_PATTERNS = [
    r"cu[aá]nto (vale|sale|cuesta|sale)\s*(una|un|la|el|mi|mis)?\s*(casa|depto|propiedad|terreno)",
    r"mejor (oferta|precio|propuesta)",
    r"negoci[oó]r",
    r"pod[eé]s (bajar|re[bv]ajar|hacer descuento)",
    r"(contrato|escriban[ií]a|impuesto|escritura|titulo|título|boleto|hipoteca)",
    r"(sucesión|sucesion|herederos|división|divisor)",
    r"(cr[eé]dito|cr[eé]dito hipotecario|pr[eé]stamo|uva|uvas)",
    r"qu[eé] (opinión|opin[áa]s|pens[aá]s|cre[eé]s|te parece|me recomen[d]?[aá]s)",
    r"es (bueno|mala|confiable|seguro)\s+(invertir|comprar|alquilar)",
    r"te (parece|parecen)",
    r"(receta|c[óo]digo|chiste|traducci[óo]n|tarea|consejo\s+de\s+salud)",
    r"(clima|temperatura|lluvia|pronóstico)",
    r"(noticia|política|f[úu]tbol|deporte)",
    r"(película|pelicula|serie|m[uú]sica|canción|cancion|libro)",
    r"c[óo]mo (programar|hacer una págin)",
    r"(javascript|código|codigo|html|css)",
    r"otr[oa]\s+(inmobiliaria|agenci|corredor)",
    r"(mejor|peor)\s+que\s+(otr[oa]|la competencia)",
    r"((zonaprop|mercadolibre|argenprop|properati)\b)",
]


def is_out_of_scope(message: str) -> bool:
    """Full out-of-scope detection. Used by webhook.py and admin endpoints."""
    msg_lower = message.lower().strip()
    return any(re.search(p, msg_lower, re.IGNORECASE) for p in _OUT_OF_SCOPE_PATTERNS)


# ── Tiebreaker ───────────────────────────────────────────────────────────────

_VALID_STATES = {
    "idle", "qualifying", "searching", "viewing_property",
    "viewing_detail", "viewing_photos", "viewing_compare",
    "scheduling_ask_date", "scheduling_ask_time", "scheduling_ask_name",
    "scheduling_confirm", "booking",
    "completed", "appointment_management", "faq",
    "out_of_scope", "handoff", "human_assistance",
}


def _normalize_state(state: str) -> Optional[str]:
    """Normalize a state name from any classifier to canonical form."""
    if not state:
        return None
    s = state.lower().strip().replace(" ", "_").replace("-", "_")
    # Map common LLM outputs to canonical states
    state_map = {
        "greeting": "qualifying",
        "saludo": "qualifying",
        "general": "idle",
        "idle": "idle",
        "qualify": "qualifying",
        "qualifying": "qualifying",
        "search": "searching",
        "searching": "searching",
        "detail": "viewing_detail",
        "viewing": "viewing_property",
        "viewingproperty": "viewing_property",
        "viewing_detail": "viewing_detail",
        "viewing_photos": "viewing_photos",
        "viewing_compare": "viewing_compare",
        "photos": "viewing_photos",
        "schedule": "scheduling_ask_date",
        "scheduling": "scheduling_ask_date",
        "booking": "scheduling_ask_date",
        "scheduling_ask_date": "scheduling_ask_date",
        "scheduling_ask_time": "scheduling_ask_time",
        "scheduling_ask_name": "scheduling_ask_name",
        "appointment": "appointment_management",
        "appointment_management": "appointment_management",
        "faq": "faq",
        "outofscope": "out_of_scope",
        "out_of_scope": "out_of_scope",
        "handoff": "human_assistance",
        "human_assistance": "human_assistance",
        "completed": "completed",
    }
    return state_map.get(s, None)


async def resolve_state(
    message: str,
    current_state: str,
    context: dict,
    history: Optional[List[dict]] = None,
) -> tuple[str, str]:
    """
    Dual classifier + tiebreaker.
    
    Returns:
        (state: str, method: str)
        method is one of: "regex", "llm", "unanimous", "regex_override", "llm_override"
    """
    # Add new_session info to context for regex classifier
    is_new_session = not history or len(history) < 2
    context["is_new_session"] = is_new_session

    # 1. Safety gate: out_of_scope from regex → verify with LLM override
    regex_result = light_regex_classify(message, current_state, context)
    if regex_result == "out_of_scope":
        if await is_legitimate_real_estate(message):
            logger.info("[Router] Out-of-scope overridden by LLM: '%s'", message[:80])
            regex_result = None  # Fall through to LLM classify
        else:
            return ("out_of_scope", "regex")

    # 2. Human assistance from fail threshold — fast path
    if regex_result == "human_assistance":
        return ("human_assistance", "regex")

    # 3. Run LLM classifier in parallel with regex
    llm_result = await llm_classify(message, current_state, context)
    llm_state = _normalize_state(llm_result)

    # 4. Regex wins if it found something obvious
    if regex_result and regex_result in _VALID_STATES:
        if regex_result == llm_state:
            return (regex_result, "unanimous")
        else:
            # Regex found something, LLM disagrees — trust regex for obvious patterns
            logger.info(
                "[Router] Regex=%s vs LLM=%s — using regex (obvious pattern)",
                regex_result, llm_state,
            )
            return (regex_result, "regex")

    # 5. LLM result — if valid, use it
    if llm_state and llm_state in _VALID_STATES:
        logger.info("[Router] Using LLM classification: %s", llm_state)
        return (llm_state, "llm")

    # 6. Nothing classified — stay in current state (don't force changes)
    logger.info("[Router] No classification — staying in current state: %s", current_state)
    return (current_state, "no_classification")


# ── Legacy helpers (kept for backward compat with _build_messages) ──────────

def detect_capability(message: str, context: dict) -> Optional[str]:
    """Legacy capability detection — simplified to just search/appointment/faq.
    Used by _build_messages for modular prompt selection.
    Returns capability name or None (LLM will use 'general')."""
    msg_lower = message.lower().strip()

    if any(kw in msg_lower for kw in ["reprogramar", "cancelar", "mis citas"]):
        return CAP_APPOINT
    if any(kw in msg_lower for kw in ["agendar", "visita", "turno", "cita",
                                       "ir a ver", "puedo ir"]):
        return CAP_SCHEDULE
    if any(kw in msg_lower for kw in ["foto", "fotos", "imagen"]):
        return CAP_DETAIL
    if any(kw in msg_lower for kw in ["horario", "dirección", "teléfono",
                                       "comisión", "consulta"]):
        return CAP_FAQ
    if any(kw in msg_lower for kw in ["busco", "quiero", "alquilar", "comprar",
                                       "departamento", "casa", "terreno", "propiedad"]):
        return CAP_SEARCH

    return None


# ── Fail counter helpers (unchanged) ─────────────────────────────────────────

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
    """Determina si se debe hacer handoff basado en contadores de fallo."""
    caps = [capability] if capability else ALL_CAPABILITIES
    for cap in caps:
        if context.get(f"{cap}_fail_count", 0) >= FAIL_THRESHOLD:
            return True
    return False
