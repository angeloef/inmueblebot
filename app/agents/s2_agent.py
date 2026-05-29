"""SimpleAgent — LLM + tool calling + structured output + escalation (Phase 3)."""

import json

from app.agents.cs_llm_client import get_client
from app.agents.schemas import CSAgentResponse as AgentResponse, CSStructuredToolCall
from app.agents.escalation import assess_confidence, build_clarification_message
from app.core.config import get_settings
settings = get_settings()
from app.core.response_parser import FINAL_RESPONSE_SCHEMA, parse_llm_response
from app.nlp.empathy import get_empathetic_prefix
from app.nlp.formality import detect_formality, get_formality_guidance
from app.nlp.coherence import build_coherence_context
from app.nlp.argentine_spanish import enrich_with_argentinisms
from app.tools.v2.registry import execute_tool, get_tools_schema


SYSTEM_PROMPT = """Eres ChatbotSerio, un asistente inmobiliario especializado en propiedades en Oberá, Misiones. 

⚠️ REGLA DE IDENTIDAD — LEÉ ESTO PRIMERO:
Sos EXCLUSIVAMENTE un asistente inmobiliario. Si el usuario pide cosas que NO son de bienes raíces (conseguir novia, recetas de cocina, chistes, consejos de vida, clima, fútbol, películas, música, hackeo, inversiones, búsqueda de trabajo, etc.), respondé ÚNICAMENTE con una variación de este mensaje y NADA MÁS:
"Soy un asistente inmobiliario. Puedo ayudarte a buscar casas, departamentos, terrenos o PH en alquiler o venta en Oberá. ¿En qué querés que te ayude?"
NO des consejos sobre el tema que preguntaron. NO sigas la conversación fuera de bienes raíces. NO improvises un personaje diferente.

Herramientas disponibles:
- search_properties: busca propiedades según operación (alquiler/venta), tipo (departamento/casa/ph/terreno), zona (Centro/UNAM/Barrio Schuster/Ruta 14), presupuesto máximo y dormitorios mínimos. Todos los filtros son opcionales.
- get_property_details: muestra todos los detalles de una propiedad específica por su ID (el número entre corchetes).
- get_property_images: muestra las fotos de una propiedad por su ID.
- get_faq_answer: responde preguntas frecuentes sobre alquiler, compra, requisitos, garantías, contrato, mascotas, visitas, zonas, precios, contacto.
- schedule_visit: agenda una visita para ver una propiedad. Parámetros: property_id (número), nombre (nombre completo del interesado), telefono (número de contacto), dia (fecha como "viernes"), horario (como "tarde" o "15:00"), consulta (cualquier pregunta adicional).
- echo: repite un mensaje de vuelta (parámetro: text).
- get_time: devuelve la fecha y hora ACTUAL (sin parámetros). NO usar para agendar visitas.

Reglas:
1. Para saludos como "hola", "buenos días", respondé con un saludo amable y breve de no más de 15 palabras. NO enumeres tus capacidades, solo saludá y preguntá en qué podés ayudar.
2. Si el usuario busca propiedades pero no especificó operación (alquiler/venta), preguntá UNA SOLA VEZ. Si el [CONTEXTO DE LA CONVERSACIÓN] ya muestra que la operación está definida (o el usuario ya la dijo en mensajes anteriores aunque con errores de tipeo), NO vuelvas a preguntar — procedé a buscar.
3. Para búsquedas, usá search_properties con los filtros del mensaje y los criterios acumulados del contexto. Si tenés al menos 2 criterios (operación + tipo), buscá YA sin pedir más aclaraciones.
4. NUNCA vuelvas a buscar si el usuario pregunta sobre resultados YA mostrados ("cuál es el más barato", "cuál tiene más ambientes"). Respondé con lo que ya sabés.
5. Si el usuario confirma un ofrecimiento ("si porfavor", "dale, mostrame"), ejecutá la acción ofrecida sin volver a buscar.
6. REGLA DE PROACTIVIDAD: Cuando el usuario muestre interés en una propiedad específica (por ID, tipo o descripción como "el monoambiente", "el de 1 dormitorio", "la primera"), usá get_property_details INMEDIATAMENTE sin pedir confirmación. NO preguntes "¿querés que te muestre los detalles?" ni "¿te paso las fotos?" — si el usuario dijo "me interesa X", eso ya es suficiente señal. Mostrá los detalles directamente.
7. Si el usuario pide MÚLTIPLES cosas en un mismo mensaje (ej: "fotos y detalles del depto 3"), planificá llamar a get_property_details primero y get_property_images después. Ejecutá ambas herramientas y respondé con toda la información junta.
8. Para preguntas sobre el proceso de alquilar/comprar, usa get_faq_answer.
9. NUNCA inventes propiedades, precios ni información.
10. Si una búsqueda no encuentra resultados, sugerí ajustar los filtros.
11. Responde SIEMPRE en español. Sé conciso, cálido y profesional.
12. Si el usuario refina la búsqueda ("solo alquiler", "en UNAM", "hasta 80 lucas"), actualizá los filtros y volvé a buscar.
   EXCEPCIÓN: Si el usuario solo dice "alquiler" o "venta" después de que YA mostraste resultados de búsqueda,
   NO vuelvas a buscar — los resultados que mostraste ya incluyen esa operación. Preguntale si quiere filtrar por algo más.
13. CRÍTICO: Cuando search_properties devuelve resultados, SIEMPRE mostrá la lista completa al usuario tal cual la devuelve la herramienta. Usá el texto EXACTO — NO reformatees, no resumas, no cambies el formato, no elimines campos. La herramienta ya formatea los resultados correctamente. Solamente si NO hay resultados, preguntá por más criterios.
14. Cuando el usuario pregunte por costos, precio mensual o servicios de una propiedad que YA mostraste, usá los datos que ya tenés. NO vuelvas a buscar. Si no tenés los datos, usá get_faq_answer.
15. NUNCA entres en un bucle de preguntas. Si ya sabés la operación (alquiler/venta) y el tipo (departamento/casa), buscá propiedades INMEDIATAMENTE aunque falten zona o presupuesto. Es mejor mostrar resultados amplios que seguir preguntando.
16. REGLA DE AGENDAMIENTO: Cuando el usuario quiera coordinar una visita, usá ÚNICAMENTE schedule_visit. NO uses get_time — esa herramienta es para preguntas sobre la hora actual, no para agendar. Recolectá property_id, nombre, teléfono, día y horario. Si faltan datos, pedilos de a uno. NO vuelvas a buscar propiedades.

FORMATO DE RESPUESTA FINAL:
Cuando ya tengas la respuesta definitiva (después de usar herramientas o si no las necesitaste), respondé SIEMPRE con este JSON exacto:
{"respuesta": "tu respuesta completa al usuario", "confianza": 0.XX}

Donde "confianza" refleja qué tan seguro estás:
- 0.95-1.0: certeza total (saludos, datos factuales de herramientas, preguntas claras)
- 0.70-0.94: bastante seguro pero la consulta es ambigua
- 0.50-0.69: entendiste parcialmente, falta información clave
- 0.00-0.49: no entendiste bien el mensaje

NUNCA respondas con texto plano. SIEMPRE usá el formato JSON con "respuesta" y "confianza"."""


async def process_message(
    message: str, session_id: str, context_prompt: str = ""
) -> AgentResponse:
    """Message in → LLM decides → tools execute → structured final response → escalation.

    Phase 5: Accepts optional belief state context for multi-turn awareness.
    """
    client = get_client()
    tools = get_tools_schema()

    system_content = SYSTEM_PROMPT
    if context_prompt:
        system_content = context_prompt + "\n\n" + SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    # Step 1: LLM decides — may return tool calls or direct answer
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        temperature=0.3,
        max_completion_tokens=1024,
    )

    choice = response.choices[0].message
    tools_called: list[str] = []
    tool_results: list[dict] = []

    # Step 2: Execute tool calls if any
    if choice.tool_calls:
        for tc in choice.tool_calls:
            parsed = CSStructuredToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments={},
            )
            try:
                parsed.arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                parsed.arguments = {}

            tools_called.append(parsed.name)
            result = await execute_tool(parsed)
            tool_results.append({"name": parsed.name, "result": result, "arguments": parsed.arguments})

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })

        # Step 3: Final response with tool results — enforce json_schema
        final_response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=0.3,
            max_completion_tokens=1024,
            response_format=FINAL_RESPONSE_SCHEMA,
        )
        raw_text = final_response.choices[0].message.content or ""
    else:
        # Direct answer (no tools) — also enforce json_schema
        raw_text = choice.content or ""

    # Step 4: Parse structured output
    final_text, raw_confidence = parse_llm_response(raw_text)

    # Step 5: Escalation
    level, confidence = assess_confidence(raw_confidence)
    escalated_text = build_clarification_message(level, final_text)

    # Step 6: NLP enrichment (Phase 10)
    escalated_text = enrich_with_argentinisms(escalated_text)
    empathetic_prefix = get_empathetic_prefix(message)
    if empathetic_prefix and not escalated_text.startswith(empathetic_prefix.strip()):
        escalated_text = empathetic_prefix + escalated_text

    return AgentResponse(
        response=escalated_text,
        tools_called=tools_called,
        raw_tool_results=tool_results,
        confidence=confidence,
    )


def _format_tool_result_for_user(tool_name: str, result: str, previous_tool: str = "") -> str:
    """Format a raw tool result into user-friendly text.

    For get_property_details — the result is already human-readable, pass through.
    For get_property_images — wrap with 📸 emoji header.
        If previous_tool was get_property_details, skip redundant details — only show photos.
    For search_properties — pass through (already formatted by the tool).
    For other tools — pass through.
    """
    if tool_name == "get_property_images":
        if previous_tool == "get_property_details":
            # Details already shown — only show photos section
            return "\U0001f4f8 **Fotos de la propiedad:**\n" + result
        return "\U0001f4f8 **Fotos de la propiedad:**\n" + result
    return result


async def process_message_multistep(
    message: str, session_id: str, context_prompt: str = ""
) -> AgentResponse:
    """Process a message that may require multiple tool calls, emitting each result as a separate chunk.

    If the LLM returns 0 or 1 tool calls, falls back to the existing process_message().
    If 2+ tool calls, executes each sequentially, collects MessageChunks, then generates a closing text.
    """
    client = get_client()
    tools = get_tools_schema()

    system_content = SYSTEM_PROMPT
    if context_prompt:
        system_content = context_prompt + "\n\n" + SYSTEM_PROMPT

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    # Step 1: LLM decides
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else None,
        temperature=0.3,
        max_completion_tokens=1024,
    )

    choice = response.choices[0].message

    # Fallback: 0 or 1 tool calls → existing single-loop processing
    if not choice.tool_calls or len(choice.tool_calls) <= 1:
        return await process_message(message, session_id, context_prompt)

    # Multistep path: 2+ tool calls
    chunks: list[MessageChunk] = []
    tools_called: list[str] = []
    tool_results: list[dict] = []
    prev_tool = ""

    for tc in choice.tool_calls:
        from app.agents.schemas import MessageChunk as MC

        parsed = CSStructuredToolCall(
            id=tc.id,
            name=tc.function.name,
            arguments={},
        )
        try:
            parsed.arguments = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            parsed.arguments = {}

        tools_called.append(parsed.name)
        result = await execute_tool(parsed)
        tool_results.append({"name": parsed.name, "result": result, "arguments": parsed.arguments})

        formatted = _format_tool_result_for_user(parsed.name, str(result), prev_tool)
        prev_tool = parsed.name
        chunks.append(MC(
            text=formatted,
            tool_used=parsed.name,
            chunk_type="tool_result",
        ))

        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(result),
        })

    # Step 3: Final LLM call for closing text
    closing_response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=0.3,
        max_completion_tokens=1024,
        response_format=FINAL_RESPONSE_SCHEMA,
    )
    raw_text = closing_response.choices[0].message.content or ""

    # Parse + escalate + enrich
    final_text, raw_confidence = parse_llm_response(raw_text)
    level, confidence = assess_confidence(raw_confidence)
    escalated_text = build_clarification_message(level, final_text)
    escalated_text = enrich_with_argentinisms(escalated_text)
    empathetic_prefix = get_empathetic_prefix(message)
    if empathetic_prefix and not escalated_text.startswith(empathetic_prefix.strip()):
        escalated_text = empathetic_prefix + escalated_text

    # Note: closing text is delivered as response, not duplicated in messages
    return AgentResponse(
        response=escalated_text,
        tools_called=tools_called,
        raw_tool_results=tool_results,
        messages=chunks,
        confidence=confidence,
    )


async def process_message_with_specialist(
    message: str,
    session_id: str,
    context_prompt: str = "",
    specialist=None,
) -> AgentResponse:
    """Process a message through a specialist agent with filtered tools.

    Args:
        specialist: Specialist dataclass with system_prompt and tool_names.
    """
    from app.tools.v2.registry import TOOL_REGISTRY

    client = get_client()

    # Filter tools to specialist subset
    specialist_tool_names = set(specialist.tool_names) if specialist else set()
    all_tools = get_tools_schema()
    filtered_tools = [
        t for t in all_tools
        if t["function"]["name"] in specialist_tool_names
    ] if specialist_tool_names else []

    # Build system prompt
    system_content = specialist.system_prompt if specialist else SYSTEM_PROMPT
    if context_prompt:
        system_content = context_prompt + "\n\n" + system_content

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    # Step 1: LLM decides with filtered tools
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        tools=filtered_tools if filtered_tools else None,
        tool_choice="auto" if filtered_tools else None,
        temperature=0.3,
        max_completion_tokens=512,
    )

    choice = response.choices[0].message
    tools_called: list[str] = []
    tool_results: list[dict] = []

    # Step 2: Execute tool calls
    import json as _json
    if choice.tool_calls:
        for tc in choice.tool_calls:
            parsed = CSStructuredToolCall(id=tc.id, name=tc.function.name, arguments={})
            try:
                parsed.arguments = _json.loads(tc.function.arguments)
            except _json.JSONDecodeError:
                parsed.arguments = {}

            tools_called.append(parsed.name)
            result = await execute_tool(parsed)
            tool_results.append({"name": parsed.name, "result": result, "arguments": parsed.arguments})

            messages.append({
                "role": "assistant", "content": None,
                "tool_calls": [{"id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}}],
            })
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

        final_response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL, messages=messages,
            temperature=0.3, max_completion_tokens=512,
            response_format=FINAL_RESPONSE_SCHEMA,
        )
        raw_text = final_response.choices[0].message.content or ""
    else:
        raw_text = choice.content or ""

    # Parse + escalate
    final_text, raw_confidence = parse_llm_response(raw_text)
    level, confidence = assess_confidence(raw_confidence)
    escalated_text = build_clarification_message(level, final_text)

    return AgentResponse(
        response=escalated_text,
        tools_called=tools_called,
        raw_tool_results=tool_results,
        confidence=confidence,
    )
