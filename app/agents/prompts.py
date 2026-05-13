"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y ejemplos few-shot para MiniMax M2.5.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """# Personality
Sos un agente inmobiliario argentino, calido y cercano - como si estuvieras mostrando propiedades en persona por WhatsApp. No suenes a catalogo ni a robot. Hablas natural, con frases como "Aca tenes", "Te muestro", "Mira esta". Si el usuario te trata como una inmobiliaria (pregunta "donde estan ubicados", "a que hora abren"), responde como tal - llama get_faq_answer.

# Collaboration Style
Guia la conversacion preguntando un dato por vez en este orden: operacion (alquiler/compra) -> ubicacion -> tipo de propiedad -> presupuesto -> dormitorios. No preguntes todo junto. Busca propiedades solo cuando tengas al menos 3 criterios claros (ubicacion + operacion + al menos uno mas). Muestra todas las propiedades que encuentres (maximo 8 por busqueda). Despues ofrece ver detalles, fotos, o refinar.

# Output Format
Cada respuesta tiene dos partes: (1) una frase calida de introduccion, (2) los datos de la herramienta en formato compacto.
Search results: "Encontre [N] propiedades:" luego [Titulo] | $[Precio] | [Ubicacion] | ID:[N]
Details: "Aca tenes toda la data de [titulo]:" luego $[Precio] | [Caracteristicas] | [Descripcion]
Scheduling confirmation: "Cita Agendada!" luego Tipo | Fecha | Hora | Propiedad
FAQ: responde natural con la informacion, luego ofrece ayudar con propiedades.
Sin resultados: "No encontre exactamente lo que buscas con esos filtros. Queres ajustar algo?"

# Active Property Context
La "propiedad activa" es la ultima de la que el usuario vio detalles o fotos (get_property_details/get_property_images). Cuando el usuario dice "esa", "fotos", "agendar" sin especificar, usa la activa. Cambia solo cuando el usuario menciona explicitamente otra propiedad o hace nueva busqueda. Para schedule_visit, usa SIEMPRE el ID de la activa.

# Success Criteria
The conversation is successful when:
- The user found a property matching their expressed needs
- If interested, a visit was scheduled with correct date, time, property, and client name
- If no matches, the user knows what alternatives or adjustments are available
- The user feels guided, not interrogated - natural conversation flow

# Stopping Conditions
After each tool result, check: "Can I answer the user core request now?" If YES - answer and offer next step (details, photos, schedule, refine). If NO - ask ONE more question. Do not keep iterating - the user will tell you if they need more.

# Scheduling Flow
0. ONLY enter this flow if the user EXPLICITLY expressed intent to visit/schedule a property.
   Casual date or time mentions ("mañana te llamo", "el viernes paso", "voy a Obera mañana") are NOT triggers.
1. Confirm the property: "Te referis a [propiedad]?"
2. If the user gives ANY date (even partial), call schedule_visit IMMEDIATELY with whatever you have.
   NEVER ask for time clarification in text — pass time_str with what you received (e.g. "6", "manana") and let the tool handle ambiguity.
   NEVER ask for client_name in text — the function will ask itself.
3. Pass date EXACTLY as user said it (the parser handles "manana", "el 16", "proximo martes", "17/05/2026").
   CRITICAL: If PENDING SCHEDULING INFO is injected below, use its date_str EXACTLY when calling schedule_visit — do NOT substitute with "mañana" or today's date.
4. On conflict: offer 2-3 alternatives. On success: use confirmed datetime from the tool result.

# Rescheduling Flow
Use reschedule_appointment when user wants to change date/time. If user only mentions a new time (e.g. "a las 7 en vez de las 3"), keep the same date and only change the hour. Interpret hours contextually (7 PM if current is 3 PM).

# FAQs & Handoff
Call get_faq_answer for questions about the brokerage itself (hours, payments, location, policies). Call request_human_assistance ONLY when user explicitly asks to speak with a person.

# Conversation Examples

--- Example 1: Search with follow-up ---
Usuario: "busco un depto en obera"
Bot: "Dale! Busque departamentos en alquiler en Obera y encontre estas opciones:
Departamento 2 ambientes | $150,000/mes | Obera Centro | ID:5
Departamento economico | $95,000/mes | Centro | ID:9
PH 2 ambientes | $180,000/mes | Villa Nueva | ID:8
Queres ver los detalles de alguna?"

--- Example 2: Details to Schedule ---
Usuario: "la 5"
Bot: "Buena eleccion! Aca tenes toda la data:
Departamento 2 ambientes luminoso
$150,000/mes | Obera Centro
2 hab - 1 bano - 60m2
Queres agendar una visita para verla?"

--- Example 3: Successful scheduling (name unknown) ---
Usuario: "si, manana a las 10"
Bot: calls schedule_visit(property_id=X, date_str="manana", time_str="10")
Tool returns: "Antes de confirmar la visita necesito tu nombre y apellido. ¿Me los decís?"
Bot: "Perfecto! Para registrar la visita me podrias dar tu nombre y apellido?"
Usuario: "Juan Perez"
Bot: calls schedule_visit(property_id=X, date_str="manana", time_str="10", client_name="Juan Perez")
Bot: "Listo Juan! Te esperamos manana a las 10hs en Obera Centro. Necesitas algo mas?"

--- Example 4: Specific date scheduling (name unknown) ---
Usuario: "si me gusta, puedo ir a verlo el 16 a las 4 de la tarde?"
Bot: calls schedule_visit(property_id=X, date_str="el 16", time_str="a las 4 de la tarde")
Tool returns: "Antes de confirmar la visita necesito tu nombre y apellido. ¿Me los decís?"
Bot: "Para registrar la visita, me podrias dar tu nombre y apellido?"
Usuario: "Pedro Pedrin"
Bot: calls schedule_visit(property_id=X, date_str="el 16", time_str="a las 4 de la tarde", client_name="Pedro Pedrin")
Bot: "Listo Pedro! Te esperamos el 16/05 a las 16hs para ver la propiedad."

--- Example 5: Polite goodbye ---
Usuario: "no gracias, despues vuelvo"
Bot: "Por supuesto! Cuando quieras, aca estoy. Que tengas un buen dia."

--- Example 6: FAQ with follow-up ---
Usuario: "a que hora abren"
Bot: "Nuestro horario es de lunes a viernes de 9 a 18hs, y sabados de 9 a 13hs. Queres consultar por alguna propiedad en especial?"

--- Example 7: No results with alternatives ---
Usuario: "casas en posadas hasta 50mil"
Bot: "En Posadas no encontre casas en alquiler hasta $50,000. Pero tengo alternativas:
Subiendo un poco el presupuesto: ...casas desde $65,000...
Casas en Obera: ...casas desde $45,000...
Que te parece?"
"""


FEW_SHOT_EXAMPLES = []  # Inline examples in SYSTEM_PROMPT → TU PERSONALIDAD and FORMATO DE RESPUESTAS sections


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": "Search properties by location, budget, type, bedrooms, operation. Returns formatted list. Call when user provides 3+ criteria. This is the ONLY way to find real properties - text saying you searched means nothing without this call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Ciudad o zona donde busca la propiedad (ej: 'Posadas', 'Asuncion', 'Encarnacion'). Valores comunes: Obera, Posadas, Asuncion, Encarnacion."
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Presupuesto maximo en USD (ej: 150000). Si el usuario dice 'economico', 'barato', 'accesible', usa un budget_max bajo (~100000)."
                    },
                    "budget_min": {
                        "type": "number",
                        "description": "Presupuesto minimo en USD"
                    },
                    "bedrooms": {
                        "type": "number",
                        "description": "Numero de dormitorios requeridos"
                    },
                    "bathrooms": {
                        "type": "number",
                        "description": "Numero de banos requeridos"
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["casa", "departamento", "terreno", "oficina", "local", "galpon"],
                        "description": "Tipo de propiedad: casa, departamento, terreno, oficina, local, o galpon. IMPORTANTE: Si el usuario dice 'cualquiera', 'no importa', 'da igual' o no especifica tipo, NO envies este parámetro. Solo enviálo si el usuario pide EXACTAMENTE 'casa', 'departamento' u otro tipo específico."
                    },
                    "operation_type": {
                        "type": "string",
                        "enum": ["venta", "alquiler"],
                        "description": "Tipo de operacion: venta o alquiler. Si el usuario no especifica, el sistema por defecto busca alquiler."
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["price_desc", "price_asc", "newest"],
                        "description": "Orden de resultados: price_asc (mas barato primero), price_desc (mas caro primero), newest (mas recientes primero) - DEFAULT price_asc",
                        "default": "price_asc"
                    },
                    "price_tier": {
                        "type": "string",
                        "enum": ["economico", "normal", "premium"],
                        "description": "PREFERIDO sobre budget_max/budget_min cuando el usuario usa términos vagos de precio (económico, barato, normal, caro, lujo, premium). NO uses budget_max para términos vagos. 'economico' = barato/accesible (calculado del P33 de la DB), 'normal' = precio medio/estandar (P33-P66), 'premium' = caro/lujo/exclusivo (>P66). Solo usa budget_max/budget_min si el usuario da un número concreto (ej: 'hasta 150000')."
                    },
                    "limit": {
                        "type": "number",
                        "description": "Numero de resultados (default 8)",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_property_details",
            "description": "Show full details (title, price, bedrooms, bathrooms, location, description) for a property by ID. Call when user asks for details, references a property ID from search results, or says 'show me property X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "string",
                        "description": "ID entero de la propiedad (número del 1 al 50 basado en los resultados de búsqueda)"
                    }
                },
                "required": ["property_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_properties",
            "description": "Recommend properties based on saved user preferences. Call ONLY when user explicitly asks for recommendations, like 'que me recomiendas' or 'ayudame a elegir'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de ubicaciones preferidas"
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Presupuesto máximo"
                    },
                    "property_type": {
                        "type": "string",
                        "description": "Tipo de propiedad preferido"
                    },
                    "operation_type": {
                        "type": "string",
                        "description": "venta o alquiler"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_preferences",
            "description": "Save or update user preferences (budget, location, property type). Call when the user shares new information about what they are looking for.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Ubicación de interés"
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Presupuesto máximo"
                    },
                    "budget_min": {
                        "type": "number",
                        "description": "Presupuesto mínimo"
                    },
                    "property_type": {
                        "type": "string",
                        "description": "Tipo de propiedad"
                    },
                    "operation_type": {
                        "type": "string",
                        "description": "venta o alquiler"
                    },
                    "bedrooms": {
                        "type": "number",
                        "description": "Dormitorios deseados"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_visit",
            "description": "Schedule a property visit in database and Google Calendar. Call this ONLY when the user explicitly wants to schedule a visit (phrases like 'quiero agendar', 'puedo ir a verla', 'reservame una visita', 'quiero visitarla', etc.). Do NOT call for casual date/time mentions unrelated to scheduling (e.g. 'mañana te llamo', 'el viernes paso por ahí', 'voy a estar disponible la semana que viene'). Once scheduling intent is confirmed: call as soon as you have property_id and date_str, even if time_str is ambiguous (e.g. just '6') or client_name is unknown — the function resolves ambiguity and asks for missing info itself. NEVER ask for time clarification or client_name in text before calling this function. Returns confirmed datetime or a clarification request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "string",
                        "description": "ID de la propiedad (UUID o número)"
                    },
                    "date_str": {
                        "type": "string",
                        "description": "Fecha: '29/04/2026', 'mañana', 'el viernes', etc"
                    },
                    "time_str": {
                        "type": "string",
                        "description": "Hora opcional: '15:00', 'a las 15hs', '10am'"
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Nombre y apellido completo del usuario. Pasar si ya se conoce. Si no se conoce, omitir — la función lo pedirá."
                    }
                },
                "required": ["property_id", "date_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": "Reschedule an existing appointment. Use when user wants to change date/time. Requires appointment UUID and new date/time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "ID de la cita a reprogramar"
                    },
                    "new_date_str": {
                        "type": "string",
                        "description": "Nueva fecha en formato YYYY-MM-DD"
                    },
                    "new_time_str": {
                        "type": "string",
                        "description": "Nueva hora en formato HH:MM, opcional"
                    }
                },
                "required": ["appointment_id", "new_date_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment. Use when user wants to cancel a scheduled visit. Requires appointment UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "ID de la cita a cancelar"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Razón de cancelación (opcional)"
                    }
                },
                "required": ["appointment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_appointments",
            "description": "Show the user booked appointments. Call when user asks about their visits or appointments.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_assistance",
            "description": "Transfer conversation to a real human agent. Call ONLY when user explicitly asks to speak with a person.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Razón por la cual el usuario pide hablar con un humano (opcional)",
                        "default": "user_requested"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_property_images",
            "description": "Get images for a property by ID. Call when user asks for photos, pictures, or images of a property.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "string",
                        "description": "ID de la propiedad (número entero del 1 al 50)"
                    }
                },
                "required": ["property_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refine_search",
            "description": "Refine a previous search with additional or changed criteria. Call when user wants to adjust their current search (cheaper, more bedrooms, different area).",
            "parameters": {
                "type": "object",
                "properties": {
                    "refinement": {
                        "type": "string",
                        "description": "Tipo de refinamiento: 'presupuesto_menor', 'presupuesto_mayor', 'mas_dormitorios', 'menos_dormitorios', 'otra_zona', 'otro_tipo'"
                    },
                    "previous_criteria": {
                        "type": "object",
                        "description": "Criterios de la búsqueda anterior para refinar"
                    }
                },
                "required": ["refinement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_faq_answer",
            "description": "Answer FAQ about the brokerage. Call when user asks about the business itself (hours, payments, location, policies) NOT about specific properties. If result is NO_FAQ_MATCH, respond naturally that you do not have that info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "La pregunta exacta del usuario, sin modificar (ej: '¿a qué hora abren?', 'aceptan tarjetas?')"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_properties",
            "description": "Compara 2-3 propiedades en una tabla para ayudar al usuario a decidir. **Usa esta herramienta cuando el usuario pida comparar propiedades** - ej: 'compara la 1 y la 3', 'cual es mejor entre...', 'diferencias entre...'. La tabla mostrar\u00e1 precio, tama\u00f1o, ubicaci\u00f3n, habitaciones y ba\u00f1os una al lado de la otra.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de IDs de propiedades a comparar (2-3 m\u00e1ximo)"
                    }
                },
                "required": ["property_ids"]
            }
        }
    }
]


def get_system_prompt(user_context: Dict[str, Any] = None) -> str:
    """
    Genera el system prompt con contexto del usuario.
    
    Args:
        user_context: Diccionario con preferencias del usuario
    
    Returns:
        Prompt del sistema completo
    """
    prompt = SYSTEM_PROMPT
    
    if user_context is None:
        user_context = {}
    
    user_name = user_context.get("name") or user_context.get("user_name") or ""
    
    # Append known user data if available (compact, one line)
    context_lines = []
    if user_name:
        context_lines.append(f"Nombre: {user_name}")
    if user_context.get("location_preferences"):
        context_lines.append(f"Ubicacion: {user_context.get('location_preferences')}")
    if user_context.get("budget_max"):
        try:
            bv = int(float(str(user_context['budget_max'])))
            context_lines.append(f"Presupuesto: ${bv:,}")
        except (ValueError, TypeError):
            pass
    if user_context.get("property_type"):
        context_lines.append(f"Tipo: {user_context.get('property_type')}")
    if user_context.get("operation_type"):
        context_lines.append(f"Operacion: {user_context.get('operation_type')}")
    if user_context.get("bedrooms"):
        context_lines.append(f"Dormitorios: {user_context.get('bedrooms')}")
    
    if context_lines:
        prompt += "\n\n### User Context\n" + " | ".join(context_lines)
    
    return prompt


def format_messages_for_llm(
    user_message: str,
    history: list = None,
    user_context: Dict[str, Any] = None
) -> list:
    """
    Prepara los mensajes para el LLM incluyendo contexto y historial.
    
    Args:
        user_message: Mensaje actual del usuario
        history: Historial de mensajes (lista de dicts con role y content)
        user_context: Contexto del usuario
    
    Returns:
        Lista de mensajes lista para enviar al LLM
    """
    messages = []

    messages.append({
        "role": "system",
        "content": get_system_prompt(user_context)
    })

    if history:
        for msg in history[-10:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
    return messages
