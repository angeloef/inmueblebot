"""System 1 router — sub-millisecond regex/keyword pattern matching.

Goal: 80% of messages never hit the LLM.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
settings = get_settings()


@dataclass
class RoutePattern:
    """A single S1 routing pattern."""

    name: str
    pattern: str
    confidence: float
    response: str = ""  # static response if handled by S1; empty if needs S2
    needs_llm: bool = False  # True = route to S2 even if matched


# ── Pattern definitions ──────────────────────────────────────────────
# Order matters: first match wins for patterns with same confidence tier.
# Patterns with needs_llm=True still consume the match but delegate to S2.

PATTERNS: list[RoutePattern] = [
    # ── GREETINGS (static S1) ──────────────────────────────────────
    RoutePattern(
        name="greeting_hola",
        pattern=r"^(hola|holis+|hola+|buen[ao]s+)\b.*$",
        confidence=0.99,
        response=f"¡Hola! Te comunicaste con {settings.INMOBILIARIA_NAME}. ¿En qué puedo ayudarte?",
    ),
    RoutePattern(
        name="greeting_formal",
        pattern=r"^(buenos días|buenas tardes|buenas noches)\b",
        confidence=0.99,
        response=f"¡{{0}}! Te comunicaste con {settings.INMOBILIARIA_NAME}. ¿En qué puedo ayudarte?",
    ),
    RoutePattern(
        name="greeting_como_estas",
        pattern=r"^(cómo|como) (estás|estas|andas|andás|va|vamos)\b",
        confidence=0.98,
        response=f"¡Muy bien, gracias! Soy el asistente de {settings.INMOBILIARIA_NAME}. ¿En qué puedo ayudarte con propiedades en Oberá?",
    ),
    # ── CONFIRMATIONS (static S1) ─────────────────────────────────
    RoutePattern(
        name="confirm_yes",
        pattern=r"^(sisi|sis[ií]|sissi|s[ií] s[ií]|si si|s[ií]|si|dale|dale dale|bueno|ok|okey|claro|obvio|por supuesto|de una|de acuerdo)\s*$",
        confidence=0.85,  # lowered so confirm_with_action catches "si + action"; bare "si" delegates to S2
        needs_llm=True,  # delegate to S2 so it can follow through on pending offers
    ),
    RoutePattern(
        name="confirm_with_action",
        pattern=r"^(s[ií]|si|dale|bueno|ok)\b.*\b(porfa|porfavor|por favor|mostrame|pasame|dame|detalles|fotos|quiero ver|mostr[aá])\b",
        confidence=0.88,
        needs_llm=True,
    ),
    RoutePattern(
        name="confirm_no",
        pattern=r"^(no|nop|nope|no gracias|ninguno|ninguna|para nada)\s*[.!]?\s*$",
        confidence=0.95,
        response="Entendido. ¿Querés que busquemos algo diferente?",
    ),
    RoutePattern(
        name="gratitude",
        pattern=r"^(?:muchas gracias|mil gracias|te agradezco|gracias)\s*[.!\s]*$",
        confidence=0.99,
        response="¡De nada! Cualquier otra cosa, avisame. 😊",
    ),
    # ── FAQ (static S1) ───────────────────────────────────────────
    RoutePattern(
        name="faq_requisitos",
        pattern=r"\b(requisitos|necesito para alquilar|qué necesito|documentos|papeles|qu[eé] piden|garant[ií]a propietaria|recibo de sueldo)\b",
        confidence=0.90,
        response=(
            "Para alquilar necesitás:\n"
            "• DNI del titular y garante\n"
            "• Recibos de sueldo (últimos 3 meses)\n"
            "• Garantía propietaria en Oberá o recibo ≥ 3x el alquiler\n"
            "• Mes de depósito + adelanto + comisión (4%)\n"
            "• Contrato mínimo 24 meses"
        ),
    ),
    RoutePattern(
        name="faq_garantia",
        pattern=r"\b(garant[ií]a|aval|respaldo|tipo de garant[ií]a)\b",
        confidence=0.92,
        response=(
            "Aceptamos dos tipos de garantía:\n"
            "1. Garantía propietaria — título de propiedad en Oberá\n"
            "2. Recibo de sueldo — ingreso neto ≥ 3x el valor del alquiler"
        ),
    ),
    RoutePattern(
        name="faq_contrato",
        pattern=r"\b(contrato|plazo|duraci[oó]n|firmar|c[uó]mo es el contrato)\b",
        confidence=0.90,
        response=(
            "Contratos por 24 meses mínimo. Incluyen:\n"
            "• Ajuste semestral por IPC\n"
            "• Depósito en garantía (1 mes)\n"
            "• Mes de adelanto\n"
            "• Comisión inmobiliaria (4% del total)"
        ),
    ),
    RoutePattern(
        name="faq_zonas",
        # Solo preguntas GENÉRICAS sobre zonas — NO frases de búsqueda como
        # "casas por esa zona" (eso debe ir al search, no al canned de zonas).
        pattern=r"\b(qu[ée] zonas|qu[ée] barrios|cu[áa]les zonas|en qu[ée] (zona|barrio)|zonas (hay|tienen|trabajan|cubren|disponibles)|barrios trabajan|d[oó]nde (hay|conviene)|qu[ée] ubicaci[oó]n)\b",
        confidence=0.88,
        response=(
            "Trabajamos en 4 zonas de Oberá:\n"
            "• Centro — todo cerca, la más cara\n"
            "• UNAM — ideal estudiantes, precios accesibles\n"
            "• Barrio Schuster — residencial, familiar, verde\n"
            "• Ruta 14 — terrenos grandes, comerciales, quintas"
        ),
    ),
    RoutePattern(
        name="faq_precios",
        pattern=r"\b(precios|cu[áa]nto (cuesta|sale|est[aá]n)|precio de referencia|cu[aá]l es el precio|rango de precios)\b",
        confidence=0.85,
        response=(
            "Precios aprox. en Oberá (2026):\n"
            "• Monoambiente: desde $40.000/mes\n"
            "• Depto 1 dorm: $55.000–$85.000/mes\n"
            "• Depto 2 dorm: $70.000–$120.000/mes\n"
            "• Casa alquiler: $65.000–$95.000/mes\n"
            "• Casa venta: desde $22.000.000\n"
            "• Terreno: desde $5.500.000"
        ),
    ),
    RoutePattern(
        name="faq_contacto",
        pattern=r"\b(contacto|tel[eé]fono|whatsapp|mail|email|hablar con|escribir|comunicarme|comunico|comunicar|contactar|contactarme|direcci[oó]n de la oficina)\b",
        confidence=0.92,
        response=(
            "Contactanos:\n"
            "• WhatsApp: +54 9 3755 123456\n"
            "• Email: info@chatbotserio.com\n"
            "• Oficina: Córdoba 450, Centro, Oberá\n"
            "• Horario: Lun-Vie 9-18hs, Sáb 9-12hs"
        ),
    ),
    RoutePattern(
        name="faq_mascotas",
        pattern=r"\b(mascotas|perro|gato|animal|aceptan mascotas|se permiten|pet friendly)\b",
        confidence=0.90,
        response="La mayoría de los departamentos no aceptan mascotas. Las casas con patio suelen ser más flexibles. Consultame por una propiedad específica.",
    ),
    # ── COMPARATIVE / ANALYTICAL (delegate to S2, don't re-search) ──
    RoutePattern(
        name="comparative_question",
        pattern=r"\b(cu[áa]l|cu[aá]les)\b.{0,80}\b(m[áa]s|menos|mayor|menor|mejor|peor|mayoría|diferencia|comparar|comparativa)\b",
        confidence=0.88,
        needs_llm=True,
    ),
    # ── SEARCH (delegate to S2) ───────────────────────────────────
    RoutePattern(
        name="search_with_type",
        pattern=r"\b(busco|quiero|necesito|buscando|estoy buscando|me interesa).{0,40}\b(depto|departamento|depa|casa|ph|terreno|lote|quincho|quinta)\b",
        confidence=0.85,
        needs_llm=True,
    ),
    RoutePattern(
        name="search_operation_only",
        pattern=r"\b(busco|quiero|necesito)\s+(alquilar|comprar|alquiler|venta|algo para alquilar|algo para comprar)\b",
        confidence=0.80,
        needs_llm=True,
    ),
    RoutePattern(
        name="search_short",
        pattern=r"\b(alquileres|alquiler|venta|propiedades|departamentos|casas)\s+(en|por)\b",
        confidence=0.78,
        needs_llm=True,
    ),
    # ── PROPERTY REFERENCES BY DESCRIPTION (delegate to S2) ───────
    RoutePattern(
        name="reference_by_type",
        pattern=r"\b(el|la|ese|esa|aquel|aquella)\s+(?:de\s+\d+\s*(?:dormitorio\w*|habitaci[oó]n\w*|ambiente\w*|ba[ñn]o\w*)|monoambiente|departamento|depto|depa|casa|ph|terreno|primero|primera|segundo|segunda|tercero|tercera|m[aá]s barato|m[aá]s caro|m[aá]s grande|m[aá]s chico|otro|otra)\b",
        confidence=0.85,
        needs_llm=True,
    ),
    # ── PROPERTY REFERENCES BY DESCRIPTION without determiner ────
    RoutePattern(
        name="reference_by_description",
        pattern=r"\b(depto|departamento|depa|casa|monoambiente|ph|terreno)\s+(para\s+estudiante|econ[oó]mico|c[eé]ntrico|con\s+balc[oó]n|de\s+\d+\s+(?:dormitorio\w*|ambiente\w*|habitaci[oó]n\w*))\b",
        confidence=0.85,
        needs_llm=True,
    ),
    # ── DETAILS / PHOTOS (delegate to S2) ──────────────────────────
    RoutePattern(
        name="show_details",
        pattern=r"\b(mostrame|mostr[aá]|ver|detalle|detalles|info|informaci[oó]n|m[aá]s (sobre|del|de))\b.*\b(\d+|el \d+|la \d+|del \d+)\b",
        confidence=0.88,
        needs_llm=True,
    ),
    RoutePattern(
        name="show_photos",
        pattern=r"\b(fotos|foto|im[aá]genes|imagen|mostr[aá] fotos|ver fotos|quiero ver)\b",
        confidence=0.90,
        needs_llm=True,
    ),
    # ── SCHEDULING (delegate to S2) ────────────────────────────────
    RoutePattern(
        name="scheduling_intent",
        pattern=r"\b(agendar|visita|visitar|coordinar|cu[áa]ndo (puedo|podemos)|horario|turno|recorrer|conocer la propiedad)\b",
        confidence=0.82,
        needs_llm=True,
    ),
    # ── IMPLICIT FEEDBACK (static S1) ──────────────────────────────
    RoutePattern(
        name="implicit_too_expensive",
        pattern=r"\b(muy caro|cuesta mucho|excede|excede mi presupuesto|no llego|se me va|fuera de presupuesto|mucho dinero|car[ií]simo)\b",
        confidence=0.75,
        response="Entiendo que el precio es alto. ¿Querés que busquemos con un presupuesto más bajo? Decime hasta cuánto podés y ajusto la búsqueda.",
    ),
    RoutePattern(
        name="implicit_too_far",
        pattern=r"\b(muy lejos|queda lejos|zona fea|no me gusta la zona|muy lejano|otra zona|m[aá]s cerca|no conozco la zona)\b",
        confidence=0.72,
        response="¿Preferís buscar en otra zona? Recordame en qué zonas de Oberá te interesa: Centro, UNAM, Barrio Schuster o Ruta 14.",
    ),
    RoutePattern(
        name="implicit_too_small",
        pattern=r"\b(muy chico|muy peque[ñn]o|poco espacio|necesito m[aá]s espacio|m[aá]s grande|no entra|muy chica)\b",
        confidence=0.72,
        response="¿Necesitás algo más amplio? Decime cuántos dormitorios o metros cuadrados buscás y ajusto la búsqueda.",
    ),
    RoutePattern(
        name="implicit_liked",
        pattern=r"\b(me gusta|me gust[oó]|me encanta|lindo|linda|hermos[oa]|qu[eé] lindo|divino|genial|espectacular|me copa|me interesa (mucho|bastante))\b",
        confidence=0.78,
        response="¡Qué bueno que te guste! ¿Querés que te muestre más detalles o agendamos una visita para verla?",
    ),
    # ── FAREWELL (static S1) ───────────────────────────────────────
    RoutePattern(
        name="farewell",
        pattern=r"\b(chau|adi[oó]s|hasta luego|nos vemos|me voy|gracias por todo|hasta pronto)\b",
        confidence=0.99,
        response="¡Chau! Cualquier cosa que necesites, ya sabés dónde encontrarme. ¡Suerte con la búsqueda! 🏠",
    ),
    # ── HELP / CAPABILITIES (static S1) ───────────────────────────
    RoutePattern(
        name="help_what_can_you_do",
        pattern=r"\b(qu[eé] (pod[eé]s|podes) hacer|ayuda|help|ayudame|qu[eé] hac[eé]s|c[oó]mo funciona|para qu[eé] serv[ií]s)\b",
        confidence=0.95,
        response=(
            "Te puedo ayudar con:\n"
            "🏠 Buscar propiedades en alquiler o venta en Oberá\n"
            "📋 Mostrarte requisitos, garantías y trámites\n"
            "📍 Información de zonas y precios\n"
            "📸 Fotos y detalles de propiedades\n"
            "📅 Agendar visitas\n\n"
            "¡Decime qué necesitás!"
        ),
    ),
]


# ── Compound-intent detection ─────────────────────────────────────────
# If any signal fires, static (needs_llm=False) patterns are suppressed
# and the message is delegated to S2.

_PROPERTY_ID = re.compile(
    r"(\[\s*\d+\s*\]|propiedad\s+\d+|\b(?:el|la|depto|departamento|casa|propiedad)\s+\d+\b)",
    re.IGNORECASE,
)
_SCHEDULING = re.compile(
    r"\b(verlo|verla|en persona|visita|visitar|visitarl[oa]|agendar|coordinar|"
    r"recorrer|cu[áa]ndo\s+(?:puedo|podemos|ir)|ir a ver|conocer la propiedad|"
    r"turno|horario para)\b",
    re.IGNORECASE,
)
_SEARCH = re.compile(
    r"\b(busco|buscando|estoy buscando|quiero\s+(?:alquilar|comprar|ver|un|una|algo)|"
    r"necesito\s+(?:alquilar|comprar|un|una|algo)|tienen algo|hay algo|"
    r"me interesa\s+(?:alquilar|comprar|un|una))\b",
    re.IGNORECASE,
)
_SPECIFIC_PRICE = re.compile(
    r"\bcu[áa]nto\s+(?:cuesta|sale|vale|est[áa])\s+(?:el|la|ese|esa|este|esta)\b",
    re.IGNORECASE,
)
_HANDOFF = re.compile(
    r"\b(hablar con\s+(?:una persona|alguien|un humano|un asesor|un agente)|"
    r"quiero hablar con|atienda una persona|un humano|persona real)\b",
    re.IGNORECASE,
)

_COMPOUND_SIGNALS = (_PROPERTY_ID, _SCHEDULING, _SEARCH, _SPECIFIC_PRICE, _HANDOFF)


def _has_compound_intent(msg: str) -> bool:
    """Return True if message carries actionable intent S1 cannot satisfy statically."""
    return any(sig.search(msg) for sig in _COMPOUND_SIGNALS)


def match_pattern(message: str) -> Optional[RoutePattern]:
    """Find the best-matching S1 pattern for a message.

    Patterns are checked in list order; the first match wins. A static
    (needs_llm=False) pattern is SKIPPED when the message also carries
    compound actionable intent (property ref, scheduling, search, specific
    price, human handoff) — those messages are delegated to S2.
    needs_llm=True patterns are never suppressed.

    Args:
        message: The user's normalized message (lowercased, trimmed).

    Returns:
        The matched RoutePattern, or None if no pattern matches.
    """
    msg = message.lower().strip()
    compound = _has_compound_intent(msg)

    for rp in PATTERNS:
        if re.search(rp.pattern, msg, re.IGNORECASE):
            # Static canned responses must not swallow compound-intent messages.
            if not rp.needs_llm and compound:
                continue
            return rp

    return None


def format_response(pattern: RoutePattern, message: str) -> str:
    """Format the pattern's response template.

    Handles {0}, {1} substitutions from regex groups.
    For needs_llm=True patterns, returns empty string.
    """
    if pattern.needs_llm:
        return ""

    msg = message.lower().strip()
    m = re.search(pattern.pattern, msg, re.IGNORECASE)

    if m and m.groups():
        try:
            return pattern.response.format(*m.groups())
        except (IndexError, KeyError):
            return pattern.response
    return pattern.response
