"""Coordinator agent — classifies intent and delegates to specialists (Phase 8).

Uses regex-first + LLM-fallback hybrid classification, then routes
to the appropriate specialist with its own tool subset and system prompt.
"""

import re
from dataclasses import dataclass
from typing import Optional

from app.agents.cs_llm_client import get_client, get_model, LLMRole
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

# Shared scope guard — appended to every specialist prompt that talks to the
# user with a free-form LLM. The keyword blocklist in router.py catches obvious
# off-topic messages cheaply; this is the LLM-level safety net for novel cases
# that "sound" real-estate-adjacent (price math, drafting emails, legal advice).
_SCOPE_GUARD = """

# ALCANCE — Qué NO hago
Solo ayudo con el negocio inmobiliario: buscar propiedades, precios de las propiedades
listadas, fotos, detalles, requisitos, zonas y agendar visitas en Oberá.
Si el usuario pide algo FUERA de eso, NO lo hago y NO doy la respuesta "igual".
Redirijo amablemente al negocio. Casos típicos a RECHAZAR:
- Cálculos matemáticos generales (ej: "cuánto es 15% de 2 millones", conversiones, intereses).
  Excepción: puedo informar el precio de una propiedad que YA está en los resultados.
- Redactar mails, cartas, mensajes o textos para terceros (dueños, inquilinos, etc.).
- Traducciones, tareas escolares, código, recetas, chistes.
- Consejos legales, fiscales, contables, médicos o financieros.
- Conocimiento general no inmobiliario.
Respuesta de redirección (variá las palabras, no la copies literal):
"Eso se escapa de lo que puedo hacer. Soy la asistente de la inmobiliaria y te puedo
ayudar con propiedades, alquileres, visitas o consultas sobre Oberá. ¿Querés que veamos algo de eso?"
"""

# ─────────────────────────────────────────────────────────────────────
# EXTENSION POINT: add new specialists here.
# Each entry is a Specialist(name, description, system_prompt, tool_names).
#   - name:        unique key, also the value returned by classify_intent
#   - description: one-line summary (used by the LLM classifier prompt)
#   - system_prompt: full instructions for the specialist LLM
#   - tool_names:  subset of registered v2 tool names this specialist may call
# To add a flow with its own `awaiting` namespace (e.g. "financing_*"),
# register the specialist here and add its prefix to _AWAITING_SPECIALIST below.
# ─────────────────────────────────────────────────────────────────────
SPECIALISTS: dict[str, Specialist] = {
    "search": Specialist(
        name="search",
        description="Property search, details, and images",
        system_prompt="""Eres el especialista en búsqueda de propiedades de ChatbotSerio.
Tu trabajo es buscar propiedades, mostrar detalles y fotos en Oberá.

Herramientas: search_properties, get_property_details, get_property_images

ZONAS DISPONIBLES EN OBERÁ (usá estos nombres exactos en el parámetro zona):
Centro, UNAM, Barrio Schuster, Ruta 14, Barrio 100 Viviendas, Barrio Copisa,
Barrio Docente, Barrio Krause, Barrio Las Palmas, Barrio Norte, Barrio San Miguel,
Hospital Samic, Terminal, Villa Stemberg

Reglas:
- SIEMPRE usá search_properties cuando el usuario quiera buscar con criterios NUEVOS.
- Pedidos de LISTAR/VER MÁS son una búsqueda NUEVA, no una pregunta sobre lo ya mostrado:
  "mostrame todos", "todos los que tengas", "qué más hay", "otras opciones", "tenés
  monoambientes", "alguno en el centro" → LLAMÁ search_properties con los filtros que
  correspondan (zona, tipo, dormitorios) y mostrá lo que encuentres.
- Cuando el usuario mencione una zona o barrio (ej: "100 viviendas", "krause", "terminal"), pasalo al parámetro zona de search_properties.
- LISTÁ los resultados de forma concreta y directa: por cada propiedad poné su [ID],
  tipo, zona, precio y dormitorios. NO respondas con generalidades ("tengo opciones en
  varias zonas") ni preguntes "¿entendí bien? confirmame" ANTES de listar. Primero mostrá,
  después ofrecé el siguiente paso (detalles, fotos o visita).
- Si la búsqueda devuelve UNA sola propiedad y ya la mostraste antes, no la repitas igual:
  aclarale que por ahora es la única que matchea y ofrecé ver detalles/fotos, coordinar
  una visita, o ampliar los criterios (otra zona, más dormitorios, otro presupuesto).
- Preguntas ANALÍTICAS sobre resultados ya mostrados ("cuál es el más barato", "cuál tiene
  más ambientes") se responden analizando los resultados previos, SIN volver a buscar.
- Si el usuario confirma un ofrecimiento ("si porfavor", "dale, mostrame"), ejecutá la acción que ofreciste (detalles o fotos).
- Cuando pidan detalles o fotos, usá la herramienta correspondiente con el ID.
- Si no hay resultados, sugerí ajustar filtros.
- Respondé en español, sé conciso y profesional.""" + _SCOPE_GUARD,
        tool_names=["search_properties", "get_property_details", "get_property_images"],
    ),
    "scheduling": Specialist(
        name="scheduling",
        description="Visit scheduling and calendar coordination",
        system_prompt="""Eres el especialista en agendamiento de visitas de ChatbotSerio.

TU ROL ES RECOPILAR DATOS. NUNCA agendás vos la visita: el sistema de confirmación
se encarga del booking automáticamente cuando tenés todos los datos. NUNCA llames
a schedule_visit (no la tenés disponible) ni confirmes en texto que la visita quedó agendada.

NUNCA menciones procesos internos del sistema. PROHIBIDO usar frases como
"te derivo al especialista", "te paso con el especialista", "voy a derivarte",
"el sistema se encargará" o cualquier referencia a derivaciones, áreas internas
o especialistas. Para el usuario, vos sos la única persona que lo atiende: hablale
en primera persona y de forma natural.

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

6. Si en [CONTEXTO DE AGENDAMIENTO] ya figura una "Propiedad seleccionada", NO preguntes
   al usuario qué propiedad quiere — ya la eligió.

7. Si falta el NOMBRE, pedilo en UNA sola oración. NUNCA pidas el teléfono — ya lo tenemos del WhatsApp del usuario.

8. El horario DEBE estar dentro de los turnos disponibles (09:00-12:00 o 15:00-18:00, sábados solo 09:00-12:00).
   Si el usuario pide un horario fuera de rango (ej: 20:00, 8pm), avisale y proponé uno dentro del rango.

9. Cuando ya tengas NOMBRE + DÍA + HORARIO, respondé ÚNICAMENTE con el resumen de confirmación,
   sin texto adicional ni menciones a sistemas o derivaciones:
   "¿Confirmo la visita para el {día} a las {horario} a nombre de {nombre}? Respondé Sí para confirmar."
   NO llames ninguna herramienta para agendar.

10. Respondé en español argentino, cálido y eficiente. Guiá al usuario naturalmente.

11. Para CONSULTAR/CONFIRMAR citas existentes — frases como "qué día me agendé",
    "me confirmas la visita", "tengo una cita?", "cuándo es mi visita", "me quedo agendado":
    → Llamá get_my_appointments (sin parámetros).

12. Para CANCELAR una cita — frases como "cancelala", "no puedo ir", "me surgió algo",
    "dejalo sin efecto": → Llamá cancel_appointment(cual="pista del día o propiedad").

13. Para REPROGRAMAR — frases como "pasala para el jueves", "movela al viernes",
    "cambiar al lunes", "mejor el martes": → Llamá reschedule_appointment(dia, horario).
    Si no hay citas para cancelar/reprogramar, informalo y ofrecé agendar una nueva.""",
        tool_names=["get_my_appointments", "cancel_appointment", "reschedule_appointment"],
    ),
    "knowledge": Specialist(
        name="knowledge",
        description="FAQ, zone info, market data, requirements",
        system_prompt="""Eres el especialista en conocimiento inmobiliario de ChatbotSerio.
Tu trabajo es responder preguntas sobre alquiler, compra, requisitos, servicios, zonas y precios en Oberá.

Herramientas: get_property_details, get_faq_answer

Zonas de Oberá donde operamos: Centro, UNAM, Barrio Schuster, Ruta 14, Barrio 100 Viviendas,
Barrio Copisa, Barrio Docente, Barrio Krause, Barrio Las Palmas, Barrio Norte,
Barrio San Miguel, Hospital Samic, Terminal, Villa Stemberg.

Reglas:
- PREGUNTAS SOBRE UNA PROPIEDAD CONCRETA (ej.: "¿el precio incluye los servicios?",
  "¿tiene cochera?", "¿acepta mascotas?") cuando en [ESTADO ACTUAL] hay una "Propiedad
  seleccionada":
    1. Primero llamá get_property_details con ese ID y fijate si la respuesta está en la
       descripción / notas / características de la propiedad.
    2. Si la info ESTÁ ahí, respondé puntualmente con ese dato de la propiedad.
    3. Si la info NO figura en la propiedad, respondé con get_faq_answer (política general).
       Aclarale al usuario que es la política general y que podés confirmar el detalle
       puntual de esa propiedad si hace falta.
- Preguntas generales (requisitos, garantías, contratos, zonas, precios de referencia):
  usá get_faq_answer directamente.
- NUNCA menciones derivaciones, "especialistas" ni procesos internos: atendés vos.
- Respondé en español argentino, informativo y claro.""" + _SCOPE_GUARD,
        tool_names=["get_property_details", "get_faq_answer"],
    ),
    "rapport": Specialist(
        name="rapport",
        description="Greetings, small talk, tone management",
        system_prompt="""Eres la asistente de la inmobiliaria. Saludás y mantenés una
conversación amable y natural. Para el usuario, VOS sos la única persona que lo atiende.

Herramienta: request_human_assistance — usala SOLO cuando el usuario pida explícitamente
hablar con una persona, un agente humano o asistencia humana.

Reglas:
- Para saludos, respondé con calidez y preguntá en qué podés ayudar.
- PROHIBIDO mencionar procesos internos o derivaciones. NUNCA digas "te derivo al
  especialista", "te paso con el asesor", "voy a derivarte", "el sistema se encargará"
  ni nada parecido. No existen "especialistas" para el usuario: lo atendés vos.
- Si el usuario expresa una necesidad concreta (buscar, agendar, preguntar precios o
  requisitos), NO anuncies una derivación: simplemente seguí la conversación y ayudalo
  vos misma (el sistema ya enruta al flujo correcto por detrás, de forma invisible).
- Si el último mensaje del bot ofreció algo y el usuario confirma ("sí", "dale"),
  interpretá ese "sí" como aceptación de esa oferta, no como charla.
- Si el usuario pide hablar con una persona o agente humano, llamá request_human_assistance.
- Respondé en español argentino, sé empática y cordial.""",
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
- Respondé en español, sé comprensivo y orientado a soluciones.""" + _SCOPE_GUARD,
        tool_names=["search_properties"],
    ),
}


# Maps an `awaiting` namespace prefix → specialist that owns that flow.
# Flow-agnostic: belief.awaiting.split("_")[0] is looked up here.
_AWAITING_SPECIALIST: dict[str, str] = {
    "scheduling": "scheduling",
}

# Detect when the user wants to visit the agency office itself (NOT a property).
_INMOBILIARIA_VISIT = re.compile(
    r"\b(la inmobiliaria|las? oficinas?|la agencia|sus oficinas|"
    r"ir a la inmobiliaria|pasar por la (oficina|inmobiliaria)|"
    r"d[oó]nde (est[aá]n|queda|los? encuentro)|la sucursal)\b",
    re.IGNORECASE,
)


def is_inmobiliaria_visit(message: str) -> bool:
    """True if the user is asking to visit the agency office (share location, not book)."""
    return bool(_INMOBILIARIA_VISIT.search(message or ""))


async def get_inmobiliaria_location() -> str:
    """Return the agency's location + business hours from the FAQ DB."""
    try:
        from app.tools.v2.get_faq_answer import get_faq_answer
        ans = await get_faq_answer("dirección y horario de la oficina")
        return (
            "Para visitar nuestra oficina no hace falta agendar, te esperamos en el horario de atención:\n\n"
            + ans
        )
    except Exception:
        return (
            "Para consultar el horario y la dirección de nuestra oficina, "
            "escribinos o llamanos directamente y te damos los detalles."
        )


# ── Intent classification (regex-first, LLM-fallback) ─────────

INTENT_PATTERNS = [
    ("scheduling", r"\b(agendar|visita|coordinar|turno|cu[áa]ndo|horario|martes|mi[eé]rcoles|jueves|viernes|lunes|s[aá]bado|domingo|agendad[ao]|cancelar|reprogramar)\b"),
    ("knowledge", r"\b(requisitos|garant[ií]a|contrato|zonas?|precios?|cu[áa]nto (cuesta|sale)|mascotas|contacto)\b"),
    ("negotiator", r"\b(muy caro|muy barato|cuesta mucho|presupuesto|no llego|se me va|rebaja|descuento|negoci|barato)\b"),
    ("rapport", r"\b(hola|chau|gracias|buenos d[ií]as|c[óo]mo (est[áa]s|andas)|ayuda|qu[ée] pod[ée]s hacer|hablar con|agente|asesor|persona|humano|llamen|llam[aá]me)\b"),
    ("search", r"\b(busco|quiero|necesito|buscando|alquilar|comprar|alquiler|venta|mostrame|detalles?|fotos?)\b"),
]


def classify_intent(message: str) -> str:
    """Classify user intent using regex-first approach with ambiguity detection.

    Returns the specialist name to delegate to.
    If multiple categories match or mixed signals are detected, falls back to
    the synchronous default — callers that support async should call
    classify_intent_async() instead.
    """
    msg = message.lower().strip()

    # Collect all matching categories instead of returning on first match
    matches: list[str] = []
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, msg):
            matches.append(intent)

    if len(matches) == 0:
        return "search"

    if len(matches) > 1:
        # Ambiguous — caller should use LLM classification; return first match as default
        return matches[0]

    # Single match — check for mixed scheduling + search signals
    has_scheduling_signal = bool(re.search(
        r'\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|ma[nñ]ana|hoy|\d+hs|\d+:\d+)\b',
        msg, re.IGNORECASE,
    ))
    has_search_signal = bool(re.search(
        r'\b(buscar|busco|quiero|necesito|ver|mostrar|departamento|casa|local)\b',
        msg, re.IGNORECASE,
    ))

    ambiguous = (
        (matches[0] == 'scheduling' and has_search_signal) or
        (matches[0] == 'search' and has_scheduling_signal)
    )
    if ambiguous:
        # Ambiguous — caller should use LLM; return the detected intent as fallback
        return matches[0]

    return matches[0]


def _is_ambiguous_intent(message: str) -> bool:
    """Return True if the message has mixed/ambiguous signals that need LLM classification."""
    msg = message.lower().strip()
    matches: list[str] = []
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, msg):
            matches.append(intent)

    if len(matches) > 1:
        return True

    if len(matches) == 1:
        has_scheduling_signal = bool(re.search(
            r'\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|ma[nñ]ana|hoy|\d+hs|\d+:\d+)\b',
            msg, re.IGNORECASE,
        ))
        has_search_signal = bool(re.search(
            r'\b(buscar|busco|quiero|necesito|ver|mostrar|departamento|casa|local)\b',
            msg, re.IGNORECASE,
        ))
        return (
            (matches[0] == 'scheduling' and has_search_signal) or
            (matches[0] == 'search' and has_scheduling_signal)
        )

    return False


async def classify_intent_llm(message: str, context_prompt: str = "") -> str:
    """Use LLM for finer-grained intent classification (fallback).

    Uses the CLASSIFY role (fast model) for low-latency classification.
    """
    client = get_client(LLMRole.CLASSIFY)

    prompt = f"""Clasificá la intención del usuario en UNA de estas categorías:
- search: buscar propiedades, ver detalles o fotos
- scheduling: agendar una visita, coordinar horario
- knowledge: preguntar sobre requisitos, garantías, servicios, zonas, precios
- negotiator: discutir precios, decir que algo es caro/barato
- rapport: saludar, despedirse, charla casual

{context_prompt}

REGLA IMPORTANTE — confirmaciones cortas:
Si el mensaje del usuario es una confirmación corta o ambigua ("sí", "si", "dale",
"ok", "listo", "bueno", "obvio"), NO lo clasifiques como 'rapport'. Mirá el ÚLTIMO
mensaje del bot en el historial: el usuario está aceptando lo que el bot ofreció.
Clasificá según ESA oferta. Ej.: si el bot ofreció decir si el precio incluye
servicios → 'knowledge'; si ofreció buscar/mostrar propiedades → 'search'; si ofreció
coordinar una visita → 'scheduling'. Solo usá 'rapport' para saludos/despedidas/charla
sin ninguna acción pendiente.

Mensaje del usuario: "{message}"

Respondé SOLO con una palabra: search, scheduling, knowledge, negotiator, o rapport."""

    response = await client.chat.completions.create(
        model=get_model(LLMRole.CLASSIFY),
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=10,
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
    if belief.selected_property_id:
        collected.append(f"  Propiedad seleccionada: #{belief.selected_property_id}")
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
    recent = [m for m in (getattr(belief, "history", None) or [])[-8:] if m]
    history_text = "\n".join(f"  - {m}" for m in recent) if recent else "  (sin historial)"

    awaiting_text = ""
    _awaiting = getattr(belief, "awaiting", None)
    if _awaiting:
        _slot_labels = {
            "scheduling_name": "el NOMBRE del interesado",
            "scheduling_day": "el DÍA de la visita",
            "scheduling_time": "el HORARIO de la visita",
            "scheduling_confirm": "la CONFIRMACIÓN final (sí/no) de la visita",
        }
        awaiting_text = (
            f"\nESTÁS ESPERANDO QUE EL USUARIO TE DÉ: "
            f"{_slot_labels.get(_awaiting, _awaiting)}.\n"
            f"Interpretá su mensaje como respuesta a esa pregunta.\n"
        )

    return f"""[CONTEXTO DE AGENDAMIENTO]{awaiting_text}

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
- Si en DATOS YA RECOLECTADOS ya figura una "Propiedad seleccionada", NO preguntes al usuario qué propiedad quiere — ya la eligió. Usá ese ID directamente.
"""


# ── Coordinator main entry ───────────────────────────────────

async def coordinate(
    message: str,
    session_id: str,
    context_prompt: str = "",
    use_agentic: bool = False,
    recent_messages: list = None,
) -> tuple[AgentResponse, str]:
    """Classify intent and delegate to the appropriate specialist.

    Args:
        use_agentic: If True, use the full Plan→Act→Observe→Evaluate loop.
        recent_messages: Optional conversation history for LLM anaphora resolution.
    """
    # Pure LLM classification — no regex heuristics
    ctx = ""
    if recent_messages:
        ctx = "Historial reciente:\n" + "\n".join(
            f"{m.get('role')}: {m.get('content', '')[:160]}" for m in (recent_messages or [])
        )
    intent = await classify_intent_llm(message, ctx)

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
            recent_messages=recent_messages,
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


async def classify_intent_with_context(
    message: str,
    belief,
    recent_messages: "list[dict] | None" = None,
) -> str:
    """Context-aware intent classification (schema v4).

    Order:
      1. If bot is awaiting a slot, route to the specialist that owns that flow.
      2. Regex classify_intent().
      3. LLM fallback when regex defaulted to search with no clear signal.
    """
    # 1. Awaiting-flow routing (flow-agnostic).
    awaiting = getattr(belief, "awaiting", None)
    if awaiting:
        prefix = awaiting.split("_")[0]
        owner = _AWAITING_SPECIALIST.get(prefix)
        if owner:
            return owner

    # Pure LLM classification
    ctx = ""
    if recent_messages:
        ctx = "Historial reciente:\n" + "\n".join(
            f"{m.get('role')}: {m.get('content', '')[:160]}" for m in (recent_messages or [])
        )
    try:
        intent = await classify_intent_llm(message, ctx)
    except Exception:
        intent = "search"

    return intent
