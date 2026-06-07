"""
Script para poblar la base de datos con FAQs de prueba.

Uso:
    python -c "import asyncio; from scripts.seed_faqs import seed_faqs; asyncio.run(seed_faqs())"

O vía async_session_factory:
    from scripts.seed_faqs import seed_faqs
    await seed_faqs()
"""
import asyncio
from loguru import logger

from app.db.session import async_session_factory
from app.db.models.faq import FAQ

FAQS = [
    # ── Horarios y atención ───────────────────────────────────────────────
    {
        "question": "¿Cuál es el horario de atención?",
        "answer": "Nuestro horario de atención es de lunes a viernes de 9:00 a 18:00 hs, y los sábados de 9:00 a 13:00 hs. También podés consultarnos por WhatsApp fuera de este horario y te responderemos a la brevedad.",
        "category": "horarios",
        "tags": ["horario", "atención", "oficina", "abren", "cierre"],
        "order": 1,
    },
    {
        "question": "¿Atención los sábados y feriados?",
        "answer": "Los sábados atendemos de 9:00 a 13:00 hs. Feriados no tenemos atención al público, pero podés dejarnos un mensaje por WhatsApp y te contactamos el siguiente día hábil.",
        "category": "horarios",
        "tags": ["sábado", "feriado", "fin de semana", "domingo"],
        "order": 2,
    },
    {
        "question": "¿Dónde están ubicados?",
        "answer": "Nuestra oficina principal está en San Martín 850, Oberá Centro, Misiones. También podés contactarnos por WhatsApp al mismo número para coordinar una visita virtual o presencial.",
        "category": "horarios",
        "tags": ["dirección", "ubicación", "oficina", "donde", "mapa"],
        "order": 3,
    },

    # ── Proceso de compra/alquiler ────────────────────────────────────────
    {
        "question": "¿Cómo es el proceso para comprar una propiedad?",
        "answer": "El proceso es: 1) Buscás la propiedad que te guste en nuestra plataforma o te la recomendamos según tus preferencias. 2) Coordinamos una visita presencial o virtual. 3) Si te gusta, hacemos una seña (10-20% del valor) para reservarla. 4) Firmamos el boleto de compra-venta con escribano. 5) Transferencia final y escrituración. Todo el proceso suele tomar entre 30 y 60 días hábiles.",
        "category": "proceso",
        "tags": ["comprar", "proceso", "pasos", "cómo comprar", "adquirir"],
        "order": 10,
    },
    {
        "question": "¿Cómo es el proceso para alquilar?",
        "answer": "Para alquilar: 1) Elegís la propiedad. 2) Coordinamos la visita. 3) Presentás la documentación requerida (DNI, recibos de sueldo, garantía). 4) Firmamos el contrato. 5) Pagás el depósito (generalmente un mes de alquiler) y el primer mes. 6) ¡Te entregamos las llaves! El proceso completo suele llevar de 3 a 7 días hábiles.",
        "category": "proceso",
        "tags": ["alquilar", "inquilino", "proceso alquiler", "cómo alquilar"],
        "order": 11,
    },
    {
        "question": "¿Qué documentos necesito para alquilar?",
        "answer": "Los documentos requeridos son: 1) DNI (frente y dorso). 2) Últimos 3 recibos de sueldo o comprobantes de ingresos. 3) Garantía propietaria o seguro de caución (según el tipo de contrato). 4) Referencias laborales y personales. 5) Si sos extranjero, también pasaporte y constancia de ingresos en el país.",
        "category": "proceso",
        "tags": ["documentos", "requisitos", "papeles", "garantía", "alquiler"],
        "order": 12,
    },
    {
        "question": "¿Qué tipos de garantía aceptan para alquiler?",
        "answer": "Aceptamos: 1) Garantía propietaria (inmueble en la misma provincia). 2) Seguro de caución (lo podés contratar con varias aseguradoras, suele costar entre 1 y 1.5 veces el valor del alquiler mensual). 3) Garantía bancaria. 4) Fianza solidaria (con recibo de sueldo). Consultanos por la mejor opción para tu caso.",
        "category": "proceso",
        "tags": ["garantía", "seguro caución", "fianza", "aval", "propietaria"],
        "order": 13,
    },
    {
        "question": "¿Cuánto tiempo toma la escrituración de una propiedad?",
        "answer": "La escrituración suele tomar entre 30 y 60 días hábiles desde la firma del boleto de compra-venta. Esto incluye: verificación de títulos, estudio de deudas (informes de dominio y catastrales), preparación de la escritura por el escribano, y firma final. Factores como la complejidad de la propiedad, el estado registral y la disponibilidad del escribano pueden acortar o extender este plazo.",
        "category": "proceso",
        "tags": ["escrituración", "tiempo", "demora", "plazo", "títulos"],
        "order": 14,
    },

    # ── Financiación y pagos ───────────────────────────────────────────────
    {
        "question": "¿Aceptan tarjetas de crédito o débito?",
        "answer": "Sí, aceptamos tarjetas de crédito y débito (Visa, Mastercard y Cabal). También aceptamos transferencia bancaria, depósito en cuenta y efectivo. Consultanos por las promociones vigentes de cuotas sin interés que tengamos con los bancos.",
        "category": "financiación",
        "tags": ["tarjeta", "crédito", "débito", "pago", "cuotas"],
        "order": 20,
    },
    {
        "question": "¿Ofrecen financiación para la compra?",
        "answer": "Trabajamos con varias opciones: 1) Créditos hipotecarios con bancos (UVA o tradicional). 2) Plan de ahorro previo. 3) Financiación directa con el propietario (sujeto a acuerdo). 4) Préstamos personales. El mejor plan depende del tipo de propiedad y tu perfil crediticio. Consultanos y te asesoramos sin compromiso.",
        "category": "financiación",
        "tags": ["financiación", "crédito", "hipotecario", "préstamo", "cuotas"],
        "order": 21,
    },
    {
        "question": "¿Cuánto sale la comisión de la inmobiliaria?",
        "answer": "Nuestra comisión es del 3% + IVA sobre el valor de venta para operaciones de compra-venta. Para alquileres, la comisión equivale a un mes de alquiler + IVA. Siempre te informamos todos los costos por adelantado, sin cargos ocultos.",
        "category": "financiación",
        "tags": ["comisión", "honorarios", "costos", "gastos", "precio"],
        "order": 22,
    },

    # ── Visitas ────────────────────────────────────────────────────────────
    {
        "question": "¿Cómo agendo una visita a una propiedad?",
        "answer": "Es muy simple. Decime qué propiedad te interesa y te ofrezco los horarios disponibles. Podés visitar de lunes a viernes de 9 a 18 hs o sábados de 9 a 13 hs. También ofrecemos visitas virtuales por videollamada si no podés acercarte.",
        "category": "visitas",
        "tags": ["visita", "agendar", "turno", "ver propiedad", "recorrer"],
        "order": 30,
    },
    {
        "question": "¿Ofrecen visitas virtuales?",
        "answer": "Sí, ofrecemos visitas virtuales por videollamada (WhatsApp Video, Zoom o Google Meet). Es ideal si estás fuera de la ciudad, tenés poco tiempo, o querés hacer un primer filtro antes de visitar presencialmente. Pedinos el turno y coordinamos.",
        "category": "visitas",
        "tags": ["virtual", "videollamada", "online", "zoom", "whatsapp video"],
        "order": 31,
    },
    {
        "question": "¿Puedo visitar una propiedad el mismo día que la veo en el chat?",
        "answer": "Si la propiedad está disponible y tenemos un horario libre, sí es posible. Consultame la propiedad que te interesa y veo la disponibilidad. A veces necesitamos coordinar con el propietario o el encargado, así que te recomiendo pedir la visita con al menos 24 horas de anticipación para garantizar el turno.",
        "category": "visitas",
        "tags": ["mismo día", "urgente", "hoy", "visita rápida", "disponibilidad"],
        "order": 32,
    },
    {
        "question": "¿La propiedad tiene muebles incluidos?",
        "answer": "Depende de la propiedad. Cada una especifica si está amoblada, semi-amoblada o vacía. Cuando te muestro los detalles de una propiedad, te indico esa información. Si tenés dudas sobre una en particular, preguntame y te lo confirmo.",
        "category": "visitas",
        "tags": ["muebles", "amoblado", "equipado", "incluye", "electrodomésticos"],
        "order": 33,
    },

    # ── Servicios y mantenimiento ──────────────────────────────────────────
    {
        "question": "¿Los servicios (luz, gas, agua) están incluídos en el alquiler?",
        "answer": "Generalmente los servicios NO están incluidos en el alquiler. El inquilino debe contratarlos y abonarlos por separado. El contrato de alquiler especifica qué servicios corren por cuenta del inquilino. En algunos casos, el expensas puede estar incluido o no — depende de lo que acordemos en el contrato.",
        "category": "servicios",
        "tags": ["servicios", "luz", "gas", "agua", "expensas", "incluido"],
        "order": 40,
    },
    {
        "question": "¿Quién se encarga de las reparaciones y el mantenimiento?",
        "answer": "El propietario se encarga de las reparaciones estructurales (goteras, problemas de electricidad general, roturas de cañerías). El inquilino se responsabiliza del mantenimiento diario y reparaciones menores (cambio de lamparitas, destapación de cañerías menores, pintura). Todo está detallado en el contrato.",
        "category": "servicios",
        "tags": ["reparaciones", "mantenimiento", "arreglos", "dueño", "responsabilidad"],
        "order": 41,
    },
    {
        "question": "¿Tienen cochera o estacionamiento?",
        "answer": "Depende de la propiedad. Algunas tienen cochera cubierta, otras estacionamiento descubierto, y otras no tienen. En los detalles de cada propiedad te indicamos si tiene cochera. Si no ves esa información, preguntame y te confirmo.",
        "category": "servicios",
        "tags": ["cochera", "garage", "estacionamiento", "auto", "vehículo", "estacionar"],
        "order": 42,
    },
    {
        "question": "¿Aceptan mascotas?",
        "answer": "Aceptamos mascotas en la mayoría de nuestras propiedades, aunque depende del reglamento del edificio o la decisión del propietario. Si tenés mascotas, decime qué tipo y tamaño así te filtro las propiedades que las aceptan. Generalmente perros y gatos chicos/medianos no tienen problema. Razas consideradas \"potencialmente peligrosas\" pueden requerir autorización especial.",
        "category": "servicios",
        "tags": ["mascotas", "perros", "gatos", "animales", "pet friendly"],
        "order": 43,
    },

    # ── Generales ──────────────────────────────────────────────────────────
    {
        "question": "¿Cuál es la diferencia entre alquiler temporario y permanente?",
        "answer": "El alquiler temporario es por períodos cortos (días, semanas, hasta 3 meses) ideal para turismo, trabajo temporal o estudios. El alquiler permanente es por contratos de 24 o 36 meses para residencia habitual. Los temporarios suelen incluir servicios y están completamente amoblados. Los permanentes son más económicos por mes pero no incluyen servicios ni suelen estar amoblados.",
        "category": "generales",
        "tags": ["temporario", "permanente", "diferencia", "corto plazo", "largo plazo"],
        "order": 50,
    },
    {
        "question": "¿Trabajan en toda la provincia o solo en Oberá?",
        "answer": "Trabajamos principalmente en Oberá y ciudades cercanas de Misiones (Posadas, Eldorado, Jardín América, Leandro Alem). También tenemos propiedades seleccionadas en Asunción, Paraguay. Si buscás en otra zona, consultame y vemos si podemos ayudarte.",
        "category": "generales",
        "tags": ["zona", "cobertura", "provincia", "misiones", "paraguay", "asunción"],
        "order": 51,
    },
    {
        "question": "¿Cómo me contacto con un agente humano?",
        "answer": "Si necesitás hablar con una persona, decime 'Quiero hablar con un agente' o 'Pásame con un humano' y te conectamos. También podés llamarnos al teléfono de la inmobiliaria o enviarnos un mensaje directo. Un asesor te va a contactar a la brevedad.",
        "category": "generales",
        "tags": ["agente", "humano", "persona", "contactar", "hablar", "asesor"],
        "order": 52,
    },
    {
        "question": "¿Publican propiedades nuevas seguido?",
        "answer": "Sí, actualizamos nuestro catálogo regularmente con nuevas propiedades. Te recomiendo que nos digas qué estás buscando (zona, tipo, presupuesto) así podemos avisarte cuando aparezca algo que te pueda interesar. También podés consultar el dashboard de propiedades para ver las últimas incorporaciones.",
        "category": "generales",
        "tags": ["nuevas", "actualización", "novedades", "publicación", "agregar"],
        "order": 53,
    },
    {
        "question": "¿Puedo publicar mi propiedad con ustedes?",
        "answer": "¡Sí! Si querés vender o alquilar tu propiedad, contactanos y te asesoramos. Evaluamos la propiedad, te recomendamos un precio de mercado, y la publicamos en nuestra plataforma + redes sociales. Nuestro equipo se encarga de las fotos y la descripción. La comisión se coordina en una reunión presencial.",
        "category": "generales",
        "tags": ["publicar", "vender", "dueño", "propietario", "tasación"],
        "order": 54,
    },
    {
        "question": "¿Hacen tasaciones?",
        "answer": "Sí, realizamos tasaciones de propiedades sin cargo. Analizamos el mercado actual, características de la propiedad, ubicación y estado para darte un valor estimado realista. Contactanos por WhatsApp o visitanos en la oficina para coordinar una visita de tasación.",
        "category": "generales",
        "tags": ["tasación", "valuación", "valor", "cuánto vale", "precio"],
        "order": 55,
    },
]


async def seed_faqs(force: bool = False):
    """Puebla la base de datos con FAQs de prueba."""
    async with async_session_factory() as session:
        from sqlalchemy import select, func
        result = await session.execute(select(func.count()).select_from(FAQ))
        count = result.scalar_one()

        if count > 0 and not force:
            logger.info(f"[FAQs] Ya existen {count} FAQs. Usá force=True para reemplazar.")
            return

        if force:
            from sqlalchemy import delete
            await session.execute(delete(FAQ))
            logger.info("[FAQs] FAQs existentes eliminadas.")

        # Scope seeded FAQs to the default tenant so they're visible under RLS
        # (FORCE ROW LEVEL SECURITY filters NULL-tenant rows).
        from app.core.tenancy import default_tenant_id
        tid = default_tenant_id()
        for faq_data in FAQS:
            faq = FAQ(tenant_id=tid, **faq_data)
            session.add(faq)

        await session.flush()
        logger.info(f"[FAQs] {len(FAQS)} FAQs insertadas correctamente.")


if __name__ == "__main__":
    asyncio.run(seed_faqs())
    print("✅ FAQs seeded!")
