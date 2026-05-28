"""FAQ tool — answers real estate questions from the dashboard-configured FAQ database."""

from app.services.faq_service import faq_service


async def get_faq_answer(pregunta: str = "") -> str:
    """Answer frequently asked questions using the dashboard FAQ database.

    Searches the faq_entries table (managed via admin dashboard) for questions
    matching the user's query. Falls back to a curated hardcoded set for topics
    not yet covered in the database.

    Args:
        pregunta: Natural-language question from the user (e.g., '¿los servicios están incluidos?')
    """
    if not pregunta.strip():
        return (
            "Puedo responder preguntas sobre requisitos, garantías, servicios, "
            "contratos, mascotas, visitas, zonas, precios y contacto. "
            "¿Sobre cuál querés información?"
        )

    # ── Try DB-backed FAQ first (dashboard-curated) ──────────────────────
    try:
        matches = await faq_service.search_faqs(pregunta, limit=3)
        if matches:
            # Return the best match — the service already scores by relevance
            best = matches[0]
            return best.answer
    except Exception:
        # Graceful fallback: DB might not be available in some environments
        pass

    # ── Fallback: curated hardcoded answers for known topics ─────────────
    return _fallback_faq(pregunta.lower().strip())


def _fallback_faq(key: str) -> str:
    """Curated answers for common topics. Extended when DB is unavailable."""
    # Try exact keyword match
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
            "Horario: Lunes a Viernes 9-18hs, Sábados 9-12hs."
        ),
    }
    if key in exact:
        return exact[key]

    # Try substring match
    for topic, answer in exact.items():
        if topic in key or key in topic:
            return answer

    # Try keyword-based matching
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
            return exact.get(topic, "No tengo información sobre ese tema todavía.")

    topics = ", ".join(sorted(exact.keys()))
    return (
        f"No tengo información específica sobre '{key}'. "
        f"Puedo responder sobre: {topics}. ¿Querés que busque algo de eso?"
    )
