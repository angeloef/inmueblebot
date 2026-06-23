"""V4 Knowledge Agent engine — KA0 scaffold.

Safety gates identical to V3 (regex, 0 LLM calls).
Stateless gates (emergency, human-handoff) fire here with v4:: labels.
Everything else delegates to V3's run_turn until KA1 installs the real engine.
"""

from __future__ import annotations

import re
import time
from uuid import UUID

from loguru import logger

# ── Safety-gate constants (verbatim from v3/engine.py) ────────────────────────

_OUT_OF_SCOPE_RESPONSE = (
    "Soy un asistente inmobiliario. "
    "Puedo ayudarte a buscar casas, departamentos, terrenos o PH en alquiler o venta. "
    "¿En qué querés que te ayude?"
)

_OUT_OF_SCOPE_PATTERNS: list[str] = [
    r"\bnovia\b", r"\bnovio\b", r"\bcita\b.*\bamorosa\b", r"\bconseguir\b.*\bnovi",
    r"\breceta\b", r"\bcocina\b", r"\bchiste\b", r"\badivinanza\b",
    r"\bclima\b", r"\bpronóstico\b", r"\btiempo\b.*\bva a\b",
    r"\bfútbol\b", r"\bfutbol\b", r"\bpartido\b.*\bjugó\b",
    r"\bpelícula\b", r"\bserie\b.*\brecomend", r"\bmúsica\b.*\bescuchar\b",
    r"\btinder\b", r"\bbumble\b", r"\bhappn\b",
    r"\bsexo\b", r"\bsexual\b", r"\bporno\b",
    r"\bhackear\b", r"\bhacker\b", r"\bcontraseña\b.*\bolvid",
    r"\bganar\s+dinero\b", r"\binvertir\b.*\bcripto\b",
    r"\bcurriculum\b", r"\bcv\b", r"\btrabajo\b.*\bbusco\b",
]

_IN_SCOPE_KEYWORDS: list[str] = [
    "alquiler", "alquilar", "alquilo", "venta", "comprar", "vender",
    "casa", "departamento", "depto", "dpto", "terreno", "ph", "duplex",
    "propiedad", "propiedades", "inmueble", "inmobiliaria", "inmobiliario",
    "obera", "oberá", "misiones", "zona", "barrio", "dormitorio",
    "presupuesto", "precio", "fotos", "detalles", "visita", "visitar",
    "requisitos", "garantía", "garantia", "contrato", "mascota",
    "servicios", "luz", "agua", "gas", "cochera", "patio", "quincho",
    "monoambiente", "ambientes", "m²", "m2", "metros", "cubiertos",
    "agendar", "coordinamos", "mostrame", "busco", "buscando",
]

_EMERGENCY = re.compile(
    r"\b(luz cortada|sin luz|corte de luz|ascensor|atrapad[oa]|inundaci[oó]n|"
    r"se inund|p[ée]rdida de agua|fuga de gas|olor a gas|escape de gas|robo|"
    r"me robaron|emergencia|accidente|ayuda urgente|incendio|fuego|"
    r"se prende fuego|me electrocut)\b",
    re.IGNORECASE,
)

_HUMAN_REQUEST = re.compile(
    r"\b(hablar con (?:una |un )?(?:persona|humano|agente|asesor|operador|representante|alguien|encargad[oa]|due[ñn][oa])"
    r"|(?:una |un )?persona real|alguien real|gente real|ser humano"
    r"|atend[ae] (?:una |un )?(?:persona|humano)"
    r"|p[aá]same? con (?:una |un |algún )?(?:persona|humano|agente|asesor|operador|representante|alguien)"
    r"|comunic[aá](?:r|me|rme)? con (?:una |un |algún )?(?:persona|humano|agente|asesor|operador|representante|alguien)"
    r"|quiero (?:un |una )?(?:agente|asesor|humano|operador|representante)"
    r"|necesito (?:un |una )?(?:agente|asesor|humano|operador|representante)"
    r"|atenci[oó]n humana|asistencia humana)\b",
    re.IGNORECASE,
)


def _is_emergency(message: str) -> bool:
    return bool(_EMERGENCY.search(message or ""))


def _is_human_request(message: str) -> bool:
    return bool(_HUMAN_REQUEST.search(message or ""))


def _contract(
    response_text: str,
    tools_used: list[str],
    rich_content: dict,
    confidence: float,
    router_label: str,
    start: float,
) -> dict:
    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "confidence": confidence,
        "router_label": router_label,
        "latency_ms": (time.perf_counter() - start) * 1000,
    }


async def run_turn(
    phone: str,
    user_message: str,
    media_url: str | None = None,
    bsuid: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    """V4 engine entry point (KA0 stub).

    Stateless safety gates fire here with v4:: labels.
    All other turns delegate to V3's run_turn until KA1 installs the real engine.
    """
    start = time.perf_counter()

    if _is_emergency(user_message):
        logger.info("[V4] Emergency gate fired for {}", phone)
        return _contract(
            "Esto parece una emergencia. Por favor llamá al 911 o al número de emergencias "
            "local. Si necesitás contactar a la inmobiliaria urgente, un asesor se va a "
            "comunicar con vos.",
            [], {}, 1.0, "v4::emergency", start,
        )

    if _is_human_request(user_message):
        logger.info("[V4] Human-handoff gate fired for {}", phone)
        return _contract(
            "Entendido, te conecto con un asesor. Te van a contactar a la brevedad.",
            ["request_human_assistance"], {}, 1.0, "v4::human-handoff", start,
        )

    # ponytail: stub delegates to V3; KA1 replaces this with the knowledge engine
    from app.routers.v3.engine import run_turn as _v3_run_turn
    return await _v3_run_turn(
        phone=phone,
        user_message=user_message,
        media_url=media_url,
        bsuid=bsuid,
        tenant_id=tenant_id,
    )
