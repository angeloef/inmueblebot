"""Coordinator agent — classifies intent and delegates to specialists (Phase 8).

Uses regex-first + LLM-fallback hybrid classification, then routes
to the appropriate specialist with its own tool subset and system prompt.
"""

import re
from dataclasses import dataclass
from typing import Optional

from app.agents.cs_llm_client import get_client, get_model
from app.agents.schemas import CSAgentResponse as AgentResponse
from app.core.config import get_settings
settings = get_settings()

# ── Specialist registry ──────────────────────────────────────

@dataclass
class Specialist:
    name: str
    description: str
    system_prompt: str
    tool_names: list[str]  # subset of available tools

SPECIALISTS: dict[str, Specialist] = {
    "search": Specialist(
        name="search",
        description="Property search, details, and images",
        system_prompt="""Eres el especialista en búsqueda de propiedades de ChatbotSerio.
Tu trabajo es buscar propiedades, mostrar detalles y fotos en Oberá.

Herramientas: search_properties, get_property_details, get_property_images

Reglas:
- SIEMPRE usá search_properties cuando el usuario quiera buscar con criterios NUEVOS.
- NUNCA vuelvas a buscar si el usuario hace una pregunta sobre resultados que YA mostraste (ej: "cuál tiene más ambientes", "cuál es el más barato"). Respondé analizando los resultados previos.
- Si el usuario confirma un ofrecimiento ("si porfavor", "dale, mostrame"), ejecutá la acción que ofreciste (detalles o fotos).
- Cuando pidan detalles o fotos, usá la herramienta correspondiente con el ID.
- Si no hay resultados, sugerí ajustar filtros.
- Respondé en español, sé conciso y profesional.""",
        tool_names=["search_properties", "get_property_details", "get_property_images"],
    ),
    "scheduling": Specialist(
        name="scheduling",
        description="Visit scheduling and calendar coordination",
        system_prompt="""Eres el especialista en agendamiento de visitas de ChatbotSerio.

Herramienta: schedule_visit — la usás SOLO cuando tengas todos los datos confirmados para agendar.

REGLAS FUNDAMENTALES:

1. LEÉ la sección [CONTEXTO DE AGENDAMIENTO] para ver qué datos ya tenés y los turnos disponibles.

2. SIEMPRE que el usuario exprese una preferencia temporal VAGA:
   - "la semana que viene" / "la próxima semana" → usá PRÓXIMA SEMANA, NUNCA ESTA SEMANA
   - "esta semana" → usá ESTA SEMANA
   - "cualquier día" → elegí el primer turno disponible (esta o próxima)
   - "a la tarde" → elegí un horario de tarde del primer día disponible
   - "en la semana" → elegí un día de semana (lunes a viernes)
   
   FORMATO: "¡Perfecto! ¿Te quedaría bien el {día} {dd/mm} a las {hh}:00 hs?"

3. Si el usuario da un DÍA concreto pero sin horario ("el viernes"):
   PROPONÉ: "El viernes {dd/mm} tengo disponible a las 10:00 o 16:00. ¿Cuál preferís?"

4. PROPONÉ UN SOLO horario cuando puedas. Solo ofrecé opciones si hay ambigüedad real.

5. NUNCA preguntes "¿qué día?" si el usuario ya expresó preferencia. PROPONÉ, no preguntes.

6. Cuando el usuario CONFIRMA ("sí", "dale", "perfecto", "me sirve", "ok", "genial"),
   O cuando ya te dio nombre + día + horario concretos en la conversación:
   Llamá a schedule_visit INMEDIATAMENTE. NO preguntes nada más.
   NUNCA confirmes una cita en texto ("te agendé", "quedó agendada") sin antes haber llamado a schedule_visit.

7. Si el usuario quiere CAMBIAR ("no, mejor el viernes", "más temprano"):
   Ajustá la propuesta y confirmá de nuevo.

8. Si falta el NOMBRE, pedilo en UNA sola oración. NUNCA pidas el teléfono — ya lo tenemos del WhatsApp del usuario.

9. Antes de llamar a schedule_visit verificá: nombre, día, horario, property_id (el teléfono NO hace falta).
   El horario DEBE estar dentro de los turnos disponibles (09:00-12:00 o 15:00-18:00, sábados solo 09:00-12:00).
   Si el usuario pide un horario fuera de rango (ej: 20:00, 8pm), avisale y proponé uno dentro del rango.

10. Respondé en español argentino, cálido y eficiente. Guiá al usuario naturalmente.

11. Para CONSULTAR/CONFIRMAR citas existentes — frases como "qué día me agendé",
    "me confirmas la visita", "tengo una cita?", "cuándo es mi visita", "me quedo agendado":
    → Llamá get_my_appointments (sin parámetros). NUNCA llames schedule_visit en este caso.

12. Para CANCELAR una cita — frases como "cancelala", "no puedo ir", "me surgió algo",
    "dejalo sin efecto": → Llamá cancel_appointment(cual="pista del día o propiedad").

13. Para REPROGRAMAR — frases como "pasala para el jueves", "movela al viernes",
    "cambiar al lunes", "mejor el martes": → Llamá reschedule_appointment(dia, horario).
    NUNCA uses schedule_visit para cambiar una cita existente.
    Si no hay citas para cancelar/reprogramar, informalo y ofrecé agendar una nueva.""",
        tool_names=["schedule_visit", "get_my_appointments", "cancel_appointment", "reschedule_appointment"],
    ),
    "knowledge": Specialist(
        name="knowledge",
        description="FAQ, zone info, market data, requirements",
        system_prompt="""Eres el especialista en conocimiento inmobiliario de ChatbotSerio.
Tu trabajo es responder preguntas sobre alquiler, compra, requisitos, zonas y precios en Oberá.

Herramienta: get_faq_answer

Reglas:
- Usá get_faq_answer para consultas sobre requisitos, garantías, contratos, zonas, precios.
- Complementá con tu conocimiento de las 4 zonas (Centro, UNAM, Barrio Schuster, Ruta 14).
- Respondé en español, sé informativo y claro.""",
        tool_names=["get_faq_answer"],
    ),
    "rapport": Specialist(
        name="rapport",
        description="Greetings, small talk, tone management",
        system_prompt="""Eres el especialista en rapport de ChatbotSerio.
Tu trabajo es saludar, mantener una conversación amable y derivar al usuario
al especialista adecuado cuando tenga una necesidad concreta.

Herramienta: request_human_assistance — usarla cuando el usuario pida explícitamente
hablar con una persona, un agente, o asistencia humana.

Reglas:
- Para saludos, respondé con calidez y preguntá en qué podés ayudar.
- Si el usuario expresa una necesidad concreta (buscar, agendar, preguntar),
  indicá que lo vas a derivar al especialista adecuado.
- Si el usuario pide hablar con una persona o agente humano, llamá request_human_assistance.
- Respondé en español, sé empático y cordial.""",
        tool_names=["request_human_assistance"],
    ),
    "negotiator": Specialist(
        name="negotiator",
        description="Price discussion, budget advice, negotiation",
        system_prompt="""Eres el especialista en negociación de ChatbotSerio.
Tu trabajo es ayudar con discusiones de precio y presupuesto.

Herramienta: search_properties (para consultar precios de referencia)

Reglas:
- Si el usuario dice que algo es caro, ofrecé alternativas más económicas.
- Consultá precios de referencia con search_properties.
- Sugerí ajustar criterios (zona más económica, menos dormitorios, etc.).
- Respondé en español, sé comprensivo y orientado a soluciones.""",
        tool_names=["search_properties"],
    ),
}


# ── Intent classification (regex-first, LLM-fallback) ─────────

INTENT_PATTERNS = [
    ("scheduling", r"\b(agendar|visita|coordinar|turno|cu[áa]ndo|horario|martes|mi[eé]rcoles|jueves|viernes|lunes|s[aá]bado|domingo|agendad[ao]|cancelar|reprogramar)\b"),
    ("knowledge", r"\b(requisitos|garant[ií]a|contrato|zonas?|precios?|cu[áa]nto (cuesta|sale)|mascotas|contacto)\b"),
    ("negotiator", r"\b(muy caro|muy barato|cuesta mucho|presupuesto|no llego|se me va|rebaja|descuento|negoci|barato)\b"),
    ("rapport", r"\b(hola|chau|gracias|buenos d[ií]as|c[óo]mo (est[áa]s|andas)|ayuda|qu[ée] pod[ée]s hacer|hablar con|agente|asesor|persona|humano|llamen|llam[aá]me)\b"),
    ("search", r"\b(busco|quiero|necesito|buscando|alquilar|comprar|alquiler|venta|mostrame|detalles?|fotos?)\b"),
]


def classify_intent(message: str) -> str:
    """Classify user intent using regex-first approach.

    Returns the specialist name to delegate to.
    """
    msg = message.lower().strip()

    # Check each pattern category
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, msg):
            return intent

    # Default: search (most common action)
    return "search"


async def classify_intent_llm(message: str, context_prompt: str = "") -> str:
    """Use LLM for finer-grained intent classification (fallback)."""
    client = get_client()

    prompt = f"""Clasificá la intención del usuario en UNA de estas categorías:
- search: buscar propiedades, ver detalles o fotos
- scheduling: agendar una visita, coordinar horario
- knowledge: preguntar sobre requisitos, garantías, zonas, precios
- negotiator: discutir precios, decir que algo es caro/barato
- rapport: saludar, despedirse, charla casual

{context_prompt}

Mensaje del usuario: "{message}"

Respondé SOLO con una palabra: search, scheduling, knowledge, negotiator, o rapport."""

    response = await client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=10,
    )

    result = (response.choices[0].message.content or "search").strip().lower()
    if result in SPECIALISTS:
        return result
    return "search"


# ── Scheduling context builder ───────────────────────────────

def _build_scheduling_context(belief) -> str:
    """Build date-aware context for the scheduling specialist.
    
    Injects today's date, available time slots for this week + next week,
    already-collected user data, and property info.
    """
    from datetime import datetime, timedelta
    
    now = datetime.now()
    weekday_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    month_names = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                   "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    
    today_str = f"{weekday_names[now.weekday()]} {now.day} de {month_names[now.month-1]} de {now.year}"
    
    # Calculate days until end of this week (Sunday)
    days_until_sunday = 6 - now.weekday()  # weekday() returns 0=Mon, 6=Sun
    
    def format_slot(d):
        """Format a single day's slot entry."""
        wd = d.weekday()
        day_name = weekday_names[wd]
        date_str = f"{day_name} {d.day:02d}/{d.month:02d}"
        if wd == 5:  # Saturday — morning only
            return f"  {date_str}: mañana 09:00-12:00"
        else:
            return f"  {date_str}: mañana 09:00-12:00, tarde 15:00-18:00"
    
    # This week (from tomorrow to Saturday, skip Sunday)
    this_week = []
    for i in range(1, days_until_sunday + 1):
        d = now + timedelta(days=i)
        if d.weekday() != 6:  # skip Sunday
            this_week.append(format_slot(d))
    
    # Next week (Monday to Saturday)
    next_monday = now + timedelta(days=days_until_sunday + 1)
    next_week = []
    for i in range(6):  # Mon-Sat
        d = next_monday + timedelta(days=i)
        if d.weekday() != 6:
            next_week.append(format_slot(d))
    
    slots_parts = []
    if this_week:
        slots_parts.append("ESTA SEMANA (quedan):")
        slots_parts.extend(this_week)
    if next_week:
        slots_parts.append("\nPRÓXIMA SEMANA:")
        slots_parts.extend(next_week)
    
    slots_text = "\n".join(slots_parts)
    
    # Collected data from belief state
    collected = []
    if belief.scheduling_name:
        collected.append(f"  Nombre: {belief.scheduling_name}")
    if belief.scheduling_phone:
        collected.append(f"  Teléfono: {belief.scheduling_phone}")
    if belief.scheduling_day:
        collected.append(f"  Día preferido: {belief.scheduling_day}")
    if belief.scheduling_time:
        collected.append(f"  Horario preferido: {belief.scheduling_time}")
    collected_text = "\n".join(collected) if collected else "  (ninguno todavía)"
    
    # Property info
    property_text = f"ID #{belief.selected_property_id}" if belief.selected_property_id else "(no especificada aún)"
    if belief.last_property_data:
        property_text += f" — {belief.last_property_data[:150]}"

    # Recent user messages — so the LLM can assemble day + time even when they
    # arrive across separate turns (e.g. "el lunes" then "a las 3 de la tarde").
    recent = [m for m in (getattr(belief, "history", None) or [])[-6:] if m]
    history_text = "\n".join(f"  - {m}" for m in recent) if recent else "  (sin historial)"

    return f"""[CONTEXTO DE AGENDAMIENTO]

HOY ES: {today_str}

TURNOS DISPONIBLES:
{slots_text}

DATOS YA RECOLECTADOS DEL USUARIO:
{collected_text}

ÚLTIMOS MENSAJES DEL USUARIO (leelos para armar la fecha completa):
{history_text}

PROPIEDAD A VISITAR: {property_text}

INSTRUCCIONES DE FECHAS:
- COMBINÁ día y horario aunque el usuario los haya dado en mensajes distintos.
  Ej: si antes dijo "el lunes" y ahora "a las 3 de la tarde", la cita es lunes 15:00 → llamá schedule_visit con dia="lunes" horario="15:00".
- "a la mañana"=10:00, "al mediodía"=12:00, "a la tarde"=15:00, "3 de la tarde"=15:00, "5 de la tarde"=17:00.
- "la semana que viene" / "la próxima semana" → usá PRÓXIMA SEMANA (nunca ESTA SEMANA)
- "dentro de N días" / "en N días" → contá N días desde HOY.
- PROPONÉ un turno concreto con día y fecha. NO preguntes "¿qué día?".
- Cuando ya tengas día + horario + nombre + property_id, llamá schedule_visit YA (no vuelvas a confirmar en texto sin llamarlo).
"""


# ── Coordinator main entry ───────────────────────────────────

async def coordinate(
    message: str,
    session_id: str,
    context_prompt: str = "",
    use_agentic: bool = False,
) -> tuple[AgentResponse, str]:
    """Classify intent and delegate to the appropriate specialist.

    Args:
        use_agentic: If True, use the full Plan→Act→Observe→Evaluate loop.
    """
    # Fast classification
    intent = classify_intent(message)

    # For ambiguous cases, use LLM
    if intent in ("search",) and not _has_clear_signal(message):
        try:
            llm_intent = await classify_intent_llm(message, context_prompt)
            if llm_intent in SPECIALISTS:
                intent = llm_intent
        except Exception:
            pass

    specialist = SPECIALISTS.get(intent, SPECIALISTS["search"])

    if use_agentic:
        from app.agents.agentic_loop import run_agentic_loop
        result = await run_agentic_loop(
            message=message,
            session_id=session_id,
            context_prompt=context_prompt,
            belief_summary=context_prompt[:500] if context_prompt else "",
            available_tools=specialist.tool_names,
        )
    else:
        from app.agents.s2_agent import process_message_with_specialist
        result = await process_message_with_specialist(
            message=message,
            session_id=session_id,
            context_prompt=context_prompt,
            specialist=specialist,
        )

    return result, specialist.name


def _has_clear_signal(message: str) -> bool:
    """Check if the message has a clear signal that doesn't need LLM re-classification."""
    msg = message.lower()
    return any(kw in msg for kw in [
        "busco", "quiero alquilar", "quiero comprar", "necesito",
        "mostrame", "detalles", "fotos", "agendar", "visita",
        "requisitos", "garantía", "hola", "chau",
    ])
