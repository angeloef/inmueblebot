"""FAQ tool — answers common real estate questions by keyword."""

from typing import Any

# FAQ database — keyword → response
FAQ_ENTRIES: dict[str, str] = {
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
    "agendar": (
        "Para agendar una visita necesito:\n"
        "  • Nombre completo\n"
        "  • Teléfono de contacto\n"
        "  • Qué propiedad querés visitar (ID)\n"
        "  • Día y horario que te quede cómodo\n"
        "Decime esos datos y lo coordinamos."
    ),
    "servicios": (
        "La mayoría de las propiedades en Oberá incluyen:\n"
        "  • Agua corriente (SAMSA)\n"
        "  • Electricidad (EMSA)\n"
        "  • Gas natural (en zona céntrica)\n"
        "Las zonas más alejadas pueden tener gas envasado (garrafa)."
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
        "  • WhatsApp: +54 9 3755 123456\n"
        "  • Email: info@chatbotserio.com\n"
        "  • Oficina: Córdoba 450, Centro, Oberá\n"
        "Horario: Lunes a Viernes 9-18hs, Sábados 9-12hs."
    ),
}


async def get_faq_answer(pregunta: str = "") -> str:
    """Answer frequently asked questions about real estate in Oberá.

    Args:
        pregunta: The FAQ keyword or question topic (e.g., 'requisitos', 'garantía', 'contrato', 'zonas').
    """
    if not pregunta.strip():
        topics = ", ".join(sorted(FAQ_ENTRIES.keys()))
        return f"Puedo responder sobre estos temas: {topics}. ¿Sobre cuál querés información?"

    # Try exact match first
    key = pregunta.lower().strip()
    if key in FAQ_ENTRIES:
        return FAQ_ENTRIES[key]

    # Try substring match
    for topic, answer in FAQ_ENTRIES.items():
        if topic in key or key in topic:
            return answer

    # Try finding keywords in the question
    keywords = {
        "requisitos": ["necesito", "documento", "papeles", "necesita", "requisito"],
        "garantía": ["garantia", "garantía", "aval", "respaldo"],
        "contrato": ["contrato", "firmar", "plazo", "duración"],
        "mascotas": ["mascota", "perro", "gato", "animal"],
        "visita": ["visitar", "ver", "conocer", "mostrar"],
        "zonas": ["zona", "barrio", "ubicación", "dónde"],
        "precios": ["precio", "cuesta", "vale", "caro", "barato", "presupuesto"],
        "contacto": ["contacto", "teléfono", "whatsapp", "email", "hablar", "escribir"],
    }

    for topic, words in keywords.items():
        if any(w in key for w in words):
            return FAQ_ENTRIES[topic]

    topics = ", ".join(sorted(FAQ_ENTRIES.keys()))
    return (
        f"No tengo información específica sobre '{pregunta}'. "
        f"Puedo responder sobre: {topics}. ¿Querés que busque algo de eso?"
    )
