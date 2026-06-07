"""FAQ tool — grounded knowledge Q&A using pgvector RAG (Phase 5).

Search order:
  1. Semantic search over knowledge_chunks (FAQ entries + property descriptions),
     returning the top-k chunks above the similarity threshold.
  2. If semantic search unavailable (pgvector not enabled, embedding API down,
     or no chunks indexed yet), fall back to keyword-based DB search.
  3. If no match found in either layer, return a safe deferral message instead of
     fabricating an answer.

The tool name and signature are unchanged (V2 contract compatibility).
"""
from __future__ import annotations

from loguru import logger

from app.services.faq_service import faq_service


async def get_faq_answer(pregunta: str = "") -> str:
    """Answer frequently asked questions using the knowledge index (pgvector RAG).

    Searches tenant knowledge chunks (FAQ entries + property descriptions) by
    semantic similarity; falls back to keyword search when RAG unavailable.
    Returns a safe deferral instead of hallucinating when nothing is found.

    Args:
        pregunta: Natural-language question from the user (e.g., '¿los servicios están incluidos?')
    """
    if not pregunta.strip():
        return (
            "Puedo responder preguntas sobre requisitos, garantías, servicios, "
            "contratos, mascotas, visitas, zonas, precios y contacto. "
            "¿Sobre cuál querés información?"
        )

    # ── 1. Semantic RAG search (Phase 5) ────────────────────────────────────
    try:
        from app.routers.v3.knowledge.index import search_knowledge
        from app.core.tenancy import resolve_tenant_id
        from app.core.config import get_settings

        settings = get_settings()
        tenant_id = resolve_tenant_id()

        chunks = await search_knowledge(
            tenant_id=tenant_id,
            query=pregunta,
            limit=settings.KNOWLEDGE_TOP_K,
            threshold=settings.KNOWLEDGE_SIMILARITY_THRESHOLD,
        )

        if chunks:
            # Log cost signal (embedding call already logged in embedder.py)
            logger.debug(
                "[RAG] get_faq_answer: {} chunks retrieved (top similarity={:.2f})",
                len(chunks),
                chunks[0]["similarity"],
            )
            return _format_rag_answer(pregunta, chunks)

    except Exception as exc:
        logger.debug("[RAG] semantic search unavailable, falling back to keyword: {}", str(exc))

    # ── 2. Keyword-based DB fallback ─────────────────────────────────────────
    try:
        matches = await faq_service.search_faqs(pregunta, limit=3)
        if matches:
            best = matches[0]
            return best.answer
    except Exception:
        pass

    # ── 3. Curated hardcoded fallback (when DB unavailable) ──────────────────
    # These answers contain Oberá-specific data (zones, utilities, office address),
    # so they're served ONLY to the default tenant. Other tenants rely on their own
    # FAQ entries in the DB and otherwise get the safe deferral below.
    try:
        from app.core.tenancy import resolve_tenant_id, default_tenant_id
        if resolve_tenant_id() == default_tenant_id():
            fallback = _fallback_faq(pregunta.lower().strip())
            if fallback is not None:
                return fallback
    except Exception:
        pass

    # ── 4. Safe deferral — nothing found, don't fabricate ────────────────────
    return (
        "No tengo información específica sobre eso en este momento. "
        "Te consulto con un asesor y te confirmo a la brevedad. "
        "¿Hay algo más en lo que pueda ayudarte?"
    )


def _format_rag_answer(query: str, chunks: list[dict]) -> str:
    """Format retrieved knowledge chunks into a coherent answer.

    When a single chunk is highly relevant (similarity ≥ 0.75), return it directly.
    When multiple chunks are moderately relevant, combine the most informative ones.
    """
    if not chunks:
        return ""

    top = chunks[0]

    # High-confidence single answer
    if top["similarity"] >= 0.75 or len(chunks) == 1:
        return top["text"]

    # Moderate confidence: combine up to 2 chunks if they cover different sources
    seen_ids = set()
    parts: list[str] = []
    for chunk in chunks[:3]:
        key = (chunk["source_type"], chunk["source_id"])
        if key not in seen_ids:
            seen_ids.add(key)
            parts.append(chunk["text"])
        if len(parts) >= 2:
            break

    return "\n\n".join(parts)


def _fallback_faq(key: str) -> str | None:
    """Curated answers for common topics. Returns None when nothing matches."""
    exact = {
        "requisitos": (
            "Para alquilar necesitás:\n"
            "  • DNI del titular y garante\n"
            "  • Recibo de sueldo (últimos 3 meses)\n"
            "  • Garantía propietaria en Oberá o recibo de sueldo equivalente a 3x el alquiler\n"
            "  • Mes de depósito + mes de adelanto + comisión inmobiliaria\n"
            "  • Contrato mínimo 24 meses"
        ),
        "garantía": (
            "Aceptamos dos tipos de garantía:\n"
            "  1. Garantía propietaria: título de propiedad en Oberá\n"
            "  2. Garantía de recibo de sueldo: ingreso neto ≥ 3 veces el valor del alquiler\n"
            "Ambas requieren verificación crediticia."
        ),
        "garantia": "La garantía puede ser propietaria (título en Oberá) o de recibo de sueldo (3x el alquiler).",
        "contrato": (
            "Todos los contratos son por 24 meses mínimo (Ley de Alquileres). Incluyen:\n"
            "  • Ajuste semestral por IPC o ICL\n"
            "  • Depósito en garantía (1 mes)\n"
            "  • Mes de adelanto\n"
            "  • Comisión inmobiliaria (4% del total del contrato)"
        ),
        "mascotas": (
            "La mayoría de los departamentos no aceptan mascotas. Las casas con patio suelen ser más flexibles.\n"
            "Consultame por una propiedad específica y te confirmo la política de mascotas."
        ),
        "visita": (
            "Las visitas se coordinan con 24-48hs de anticipación. Necesitamos:\n"
            "  • Tu nombre completo y teléfono\n"
            "  • Día y horario preferido\n"
            "  • ID de la propiedad que querés ver\n"
            "Te confirmamos por WhatsApp cuando esté agendada."
        ),
        "servicios": (
            "Los servicios (luz, agua, gas) NO están incluidos en el precio del alquiler. "
            "El inquilino los contrata y paga por separado.\n\n"
            "En Oberá funcionan:\n"
            "  • Agua: SAMSA\n"
            "  • Electricidad: EMSA\n"
            "  • Gas natural (zona céntrica) o gas envasado (zonas alejadas)"
        ),
        "zonas": (
            "Trabajamos en 4 zonas principales de Oberá:\n"
            "  • Centro — la más cara, todo cerca\n"
            "  • UNAM — ideal estudiantes, precios accesibles\n"
            "  • Barrio Schuster — residencial, familiar, verde\n"
            "  • Ruta 14 — terrenos grandes, comerciales, quintas\n"
            "¿En qué zona preferís buscar?"
        ),
        "precios": (
            "Precios de referencia en Oberá (2026):\n"
            "  • Monoambiente: desde $40,000/mes (alquiler)\n"
            "  • Depto 1 dorm.: $55,000–$85,000/mes\n"
            "  • Depto 2 dorm.: $70,000–$120,000/mes\n"
            "  • Casa: $65,000–$95,000/mes\n"
            "  • Terreno: desde $5,500,000 (venta)\n"
            "  • Casa en venta: desde $22,000,000\n"
            "Estos son aproximados. Buscá con tu presupuesto para ver opciones reales."
        ),
        "contacto": (
            "Podés contactarnos por:\n"
            "  • WhatsApp: +54 9 3755 5289339\n"
            "  • Oficina: Córdoba 450, Centro, Oberá\n"
            "Horario: Lunes a Viernes 9-18hs, Sábados 9-13hs."
        ),
    }
    if key in exact:
        return exact[key]

    for topic, answer in exact.items():
        if topic in key or key in topic:
            return answer

    keywords = {
        "requisitos": ["necesito", "documento", "papeles", "necesita", "requisito"],
        "garantía": ["garantia", "garantía", "aval", "respaldo"],
        "contrato": ["contrato", "firmar", "plazo", "duración"],
        "mascotas": ["mascota", "perro", "gato", "animal"],
        "servicios": ["servicio", "luz", "agua", "gas", "incluye", "incluido", "expensas"],
        "visita": ["visitar", "ver", "conocer", "mostrar"],
        "zonas": ["zona", "barrio", "ubicación", "dónde"],
        "precios": ["precio", "cuesta", "vale", "caro", "barato", "presupuesto"],
        "contacto": ["contacto", "teléfono", "whatsapp", "email", "hablar", "escribir"],
    }
    for topic, words in keywords.items():
        if any(w in key for w in words):
            return exact.get(topic)

    return None
