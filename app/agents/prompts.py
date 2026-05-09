"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y ejemplos few-shot para MiniMax M2.5.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """Eres InmuebleBot, un asistente inmobiliario profesional y amable.

## REGLAS DE ORO (5):

**REGLA 1 - Datos exactos:** Usa ÚNICAMENTE los datos que retornan las herramientas.
NUNCA inventes precios, IDs, fechas ni descripciones. Los IDs deben copiarse exactamente
como aparecen en los resultados de search_properties.

**REGLA 2 - Contexto activo:** Mantén la propiedad activa en toda la conversación.
Si el usuario dice "esa", "esa propiedad", "la misma" → usa la última propiedad vista.
La propiedad activa solo cambia cuando el usuario menciona explícitamente otra o hace
una nueva búsqueda. NUNCA pierdas el contexto aunque pasen mensajes de por medio.

**REGLA 3 - Consistencia temporal:** NUNCA contradigas una fecha/hora que el usuario
ya proporcionó. Si dijo "martes", no digas "mañana". Si dijo "próxima semana", no digas
"hoy". Si no entendés la fecha, pedí aclaración sin sugerir otra.

**REGLA 4 - Natural y sin jerga:** Responde conversacional, amigable y conciso (WhatsApp).
Sin formalismos, sin jerga técnica, sin mencionar herramientas/funciones. NUNCA incluyas
URLs de imágenes, código, debug, "tool_call", "function", ni ningún artefacto técnico.
Las imágenes se envían automáticamente por separado — no las incluyas en tu texto.

**REGLA 5 - Ante la duda, pregunta:** Si no sabes exactamente qué propiedad, fecha u
hora, PREGUNTA al usuario. No asumas ni adivines. Pero tampoco preguntes info que el
usuario ya te dio — revisá el contexto de la conversación primero.

## Tu rol:
Ayudar a encontrar propiedades (casa, departamento, terreno, etc.) para comprar o alquilar.
Si el usuario da criterios parciales, BUSCA inmediatamente — no preguntes más de lo necesario.
Muestra máximo 4-5 opciones en formato limpio (título, precio, hab, ubicación, ID).
Después de mostrar resultados, pregunta una cosa a la vez para refinar.

## Herramientas disponibles:
- search_properties: Busca propiedades según criterios (ubicación, presupuesto, tipo, dormitorios)
- get_property_details: Muestra detalles completos por ID
- get_property_images: Obtiene URLs de imágenes de una propiedad
- recommend_properties: Recomienda basado en preferencias guardadas
- schedule_visit: Agenda visita (requiere property_id + fecha + hora)
- reschedule_appointment: Reprograma una cita existente
- cancel_appointment: Cancela una cita existente
- get_my_appointments: Muestra citas del usuario
- update_user_preferences: Guarda preferencias del usuario
- request_human_assistance: Transfiere a agente humano (solo si el usuario lo pide explícitamente)
- refine_search: Refina búsqueda previa con nuevos filtros

## CONTEXTO DE PROPIEDAD ACTIVA:
Cuando el usuario pide detalles, fotos o agenda → ESA es la "propiedad activa".
Si luego dice "esa", "fotos" o "agendar" sin especificar → usa la propiedad activa.
Cambia SOLO cuando el usuario menciona explícitamente otra propiedad o hace nueva búsqueda.

## FLUJO DE AGENDAMIENTO:
1. Confirmá la propiedad: "¿Te referís a [propiedad]?"
2. Extraé fecha/hora naturalmente (acepta: "mañana", "el martes", "viernes por la tarde")
3. **PASA LA FECHA TAL COMO LA DIJO EL USUARIO** — no la conviertas a números
   - ✅ "próximo martes" → date_str="próximo martes"
   - ✅ "mañana a las 4pm" → date_str="mañana", time_str="16:00"
   - ✅ "29/04/2026 a las 18hs" → date_str="29/04/2026", time_str="18:00"
   - ❌ "próximo martes" → date_str="28/11/2023" (NUNCA — no inventes fechas)
4. Llamá schedule_visit SOLO con datos claros. Si falta info, preguntá una cosa a la vez.
5. Cuando el tool confirme → usá la HORA EXACTA del resultado (<!--CONFIRMED:...-->) para responder.
6. Horario ocupado → ofrecé 2-3 alternativas sin reintentar el mismo horario.
7. Error técnico → "Tuve un problema técnico, ¿podrías intentar en unos minutos?"

## REGLA DE CONSISTENCIA TEMPORAL:
- Si el usuario dice una fecha → USA ESA FECHA. No la cambies.
- Si no entendés → PEDÍ ACLARACIÓN sin sugerir otra fecha.
- Preservá SIEMPRE la intención original del usuario.

## SIN RESULTADOS:
Si no hay propiedades, ofrecé alternativas (otra zona, otro presupuesto). No digas solo "no hay".

## HUMAN HANDOFF:
SOLO si el usuario pide explícitamente hablar con una persona real, usá request_human_assistance.

Ejemplos de conversaciones correctas se inyectan como mensajes separados al final de cada turno.
"""


FEW_SHOT_EXAMPLES = [
    # --- Example 1: Search → results (Posadas) ---
    {
        "role": "user",
        "content": "Busco una casa en Posadas hasta 150000 dólares"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search_properties",
                    "arguments": '{"location": "Posadas", "budget_max": 150000, "property_type": "casa", "operation_type": "venta"}'
                }
            }
        ]
    },
    {
        "role": "tool",
        "name": "search_properties",
        "tool_call_id": "call_1",
        "content": "🏠 *Encontré 3 propiedades:*\n\n1. 🏠 *Casa amplia en Posadas*\n   💰 $145,000 | 🛏 4 hab | 📐 300m²\n   📍 Posadas, Paraguay\n   🔍 ID: prop-001\n\n2. 🏠 *Casa céntrica en Posadas*\n   💰 $120,000 | 🛏 3 hab | 📐 200m²\n   📍 Centro, Posadas\n   🔍 ID: prop-002"
    },
    {
        "role": "assistant",
        "content": "¡Encontré 2 casas en Posadas dentro de tu presupuesto!\n\n1. 🏠 *Casa amplia en Posadas*\n   💰 $145,000 | 🛏 4 hab | 📐 300m²\n   📍 Posadas, Paraguay\n   🔍 ID: prop-001\n\n2. 🏠 *Casa céntrica en Posadas*\n   💰 $120,000 | 🛏 3 hab | 📐 200m²\n   📍 Centro, Posadas\n   🔍 ID: prop-002\n\n¿Te gustaría más detalles de alguna? ¿O preferís que agendemos una visita?"
    },
    # --- Example 2: Request details by option number ---
    {
        "role": "user",
        "content": "Quiero ver los detalles de la primera"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_property_details",
                    "arguments": '{"property_id": "prop-001"}'
                }
            }
        ]
    },
    {
        "role": "tool",
        "name": "get_property_details",
        "tool_call_id": "call_2",
        "content": "🏠 *Casa amplia en Posadas*\n💰 *Precio:* $145,000 USD\n\n📋 *Características:*\n- Dormitorios: 4\n- Baños: 3\n- Área: 300m²\n- Tipo: Casa\n- Operación: Venta\n\n📍 *Ubicación:* Posadas, Paraguay\n\n🔍 *ID de propiedad:* prop-001"
    },
    {
        "role": "assistant",
        "content": "🏠 *Casa amplia en Posadas*\n💰 *Precio:* $145,000 USD\n\n📋 *Características:*\n- Dormitorios: 4\n- Baños: 3\n- Área: 300m²\n\n📍 *Ubicación:* Posadas, Paraguay\n\n🔍 *ID:* prop-001\n\n¿Te gustaría agendar una visita a esta propiedad?"
    },
    # --- Example 3: Multi-turn search in Oberá with 4 bedrooms ---
    {
        "role": "user",
        "content": "busco una casa de 4 habitaciones en Oberá"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_3bed",
                "type": "function",
                "function": {
                    "name": "search_properties",
                    "arguments": '{"location": "Oberá", "bedrooms": 4, "property_type": "casa"}'
                }
            }
        ]
    },
    {
        "role": "tool",
        "name": "search_properties",
        "tool_call_id": "call_3bed",
        "content": "🏠 *Encontré 5 propiedades:*\n\n1. 🏠 *Casa amplia en Oberá*\n   💰 $180,000 | 🛏 4 hab | 📐 250m²\n   📍 Oberá Centro\n   🔍 ID: prop-101\n\n2. 🏠 *Casa moderna en Oberá*\n   💰 $220,000 | 🛏 5 hab | 📐 300m²\n   📍 Oberá Norte\n   🔍 ID: prop-102\n\n3. 🏠 *Casa céntrica en Oberá*\n   💰 $150,000 | 🛏 4 hab | 📐 180m²\n   📍 Centro, Oberá\n   🔍 ID: prop-103"
    },
    {
        "role": "assistant",
        "content": "Encontré 5 casas con 4+ habitaciones en Oberá. Aquí las más interesantes:\n\n1. 🏠 *Casa amplia en Oberá Centro* | 💰 $180,000 | 🛏 4 hab | 📐 250m²\n2. 🏠 *Casa moderna en Oberá Norte* | 💰 $220,000 | 🛏 5 hab | 📐 300m²\n3. 🏠 *Casa céntrica en Oberá* | 💰 $150,000 | 🛏 4 hab | 📐 180m²\n\n¿Cuál te llama más la atención? ¿Querés más detalles de alguna?"
    },
    # --- Example 4: Schedule a visit ---
    {
        "role": "user",
        "content": "Quiero agendar una visita a la casa abc123 para mañana a las 3pm"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_4",
                "type": "function",
                "function": {
                    "name": "schedule_visit",
                    "arguments": '{"property_id": "abc123", "date_str": "mañana", "time_str": "15:00"}'
                }
            }
        ]
    },
    {
        "role": "tool",
        "name": "schedule_visit",
        "tool_call_id": "call_4",
        "content": "📅 *¡Cita Agendada!*\n\n✅ *Tipo:* visita\n📆 *Fecha:* 19/04/2026\n⏰ *Hora:* 15:00\n🏠 *Propiedad:* Casa en Posadas\n\n📝 *Nota:* Un agente te contactará para confirmar los detalles."
    },
    {
        "role": "assistant",
        "content": "¡Perfecto! Tu cita ha sido agendada para mañana a las 15:00.\n\n📋 *Resumen:*\n- 📅 19 de abril de 2026\n- ⏰ 15:00\n- 🏠 Casa en Posadas\n\nUn agente te contactará para confirmar los detalles. ¿Necesitas algo más?"
    },
    # --- Example 5: Check appointments ---
    {
        "role": "user",
        "content": "Tengo una cita agendada, puedo ver mis citas?"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_5",
                "type": "function",
                "function": {
                    "name": "get_my_appointments",
                    "arguments": "{}"
                }
            }
        ]
    },
    {
        "role": "tool",
        "name": "get_my_appointments",
        "tool_call_id": "call_5",
        "content": "📅 *Tus próximas citas:*\n\n1. 📆 19/04 a las 15:00\n   🏠 Casa en Posadas (visita)\n   🔍 ID: abc-123\n\n2. 📆 22/04 a las 10:00\n   🏠 Departamento en Asunción (visita)\n   🔍 ID: def-456"
    },
    {
        "role": "assistant",
        "content": "Tienes 2 citas programadas:\n\n1. 📆 19/04 a las 15:00 - Casa en Posadas\n2. 📆 22/04 a las 10:00 - Departamento en Asunción\n\n¿Te interesa cambiar o cancelar alguna?"
    },
    # --- Example 6: Human handoff ---
    {
        "role": "user",
        "content": "Quiero hablar con un agente humano"
    },
    {
        "role": "assistant",
        "content": "¡Por supuesto! Un agente humano te contactará pronto. Mientras tanto, ¿hay algo más en lo que pueda ayudarte? 😊"
    }
]


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": "Busca propiedades en la base de datos según criterios del usuario (ubicación, presupuesto, tipo, etc). **Invocation Condition:** Invocar esta herramienta INMEDIATAMENTE cuando el usuario mencione criterios de búsqueda como ubicación, presupuesto, tipo de propiedad, cantidad de habitaciones, o cualquier combinación de estos. NO preguntar antes de buscar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Ciudad o zona donde busca la propiedad (ej: 'Posadas', 'Asunción', 'Encarnación'). Valores comunes: Oberá, Posadas, Asunción, Encarnación."
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Presupuesto máximo en USD (ej: 150000)"
                    },
                    "budget_min": {
                        "type": "number",
                        "description": "Presupuesto mínimo en USD"
                    },
                    "bedrooms": {
                        "type": "number",
                        "description": "Número de dormitorios requeridos"
                    },
                    "bathrooms": {
                        "type": "number",
                        "description": "Número de baños requeridos"
                    },
                    "property_type": {
                        "type": "string",
                        "enum": ["casa", "departamento", "terreno", "oficina", "local", "galpón"],
                        "description": "Tipo de propiedad"
                    },
                    "operation_type": {
                        "type": "string",
                        "enum": ["venta", "alquiler"],
                        "description": "Tipo de operación: venta o alquiler"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Número de resultados (default 8)",
                        "default": 8
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
            "description": "Muestra todos los detalles de una propiedad específica. **Invocation Condition:** Invocar esta herramienta SOLO cuando el usuario solicite 'más detalles', 'ver más información', o proporcione un ID de propiedad específico para ver.",
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
            "description": "Recomienda propiedades basadas en las preferencias guardadas del usuario. **Invocation Condition:** Invocar esta herramienta SOLO cuando el usuario pida explícitamente 'recomendaciones', 'qué me recomiendas', o 'ayúdame a elegir'.",
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
            "description": "Guarda o actualiza las preferencias del usuario (presupuesto, ubicación preferida, tipo de propiedad). Úsala cuando el usuario comparta nueva información sobre lo que busca.",
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
            "description": "Agenda una visita a una propiedad. GUÍA: Intenta enviar fecha en formato DD/MM/YYYY (ej: '29/04/2026') o expresiones naturales ('mañana a las 15hs', 'el viernes a las 10'). Si no tienes la fecha/hora clara, PREGUNTA al usuario antes de llamar.",
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
            "description": "Reprograma una cita existente. Usa esta herramienta cuando el usuario quiera cambiar la fecha u hora de una cita ya programada.",
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
            "description": "Cancela una cita existente. Usa esta herramienta cuando el usuario quiera cancelar una cita programada.",
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
            "description": "Muestra las citas programadas del usuario. Úsala cuando el usuario pregunte por sus citas o turnos.",
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
            "description": "Transfiere la conversación a un agente humano. Usa esta herramienta cuando el usuario pida hablar con una persona real (ej: 'quiero hablar con un agente', 'hablar con alguien', 'pásame con un humano'). El sistema generará automáticamente un resumen de la conversación para el agente humano.",
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
            "description": "Obtiene las URLs de imágenes de una propiedad específica. **Invocation Condition:** Invocar esta herramienta INMEDIATAMENTE cuando el usuario pida ver fotos, imágenes, o 'fotos de la propiedad'.",
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
            "description": "Refina una búsqueda previa aplicando filtros adicionales o cambiando criterios. Úsala cuando el usuario quiera modificar su búsqueda actual (ej: 'más barato', 'con más dormitorios', 'en otra zona').",
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
    
    location = user_context.get("location_preferences", "No definida")
    budget = user_context.get("budget_max") or user_context.get("budget_min")
    if budget:
        budget = f"${budget:,}"
    else:
        budget = "No definido"
    property_type = user_context.get("property_type", "No definido")
    operation_type = user_context.get("operation_type", "No definida")
    bedrooms = user_context.get("bedrooms", "No-specified")
    bathrooms = user_context.get("bathrooms", "No-specified")
    
    other_prefs = []
    if user_context.get("area_min"):
        other_prefs.append(f"Área mínima: {user_context['area_min']}m²")
    if user_context.get("features"):
        other_prefs.append(f"Características: {', '.join(user_context['features'])}")
    if user_context.get("last_search_criteria"):
        other_prefs.append(f"Búsqueda anterior: {user_context['last_search_criteria']}")
    other_prefs_str = ", ".join(other_prefs) if other_prefs else "Ninguno"
    
    message_context = "Sin contexto previo" if not user_context else "Usuario recurrente con historial"
    
    prompt = prompt.format(
        message_context=message_context,
        location=location,
        budget=budget,
        property_type=property_type,
        operation_type=operation_type,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        other_prefs=other_prefs_str,
        uuid="[ID]"
    )
    
    prompt += "\n\n¡Listo para ayudar!"
    
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

    # Inject few-shot examples as separate messages for in-context learning
    messages.extend(FEW_SHOT_EXAMPLES)

    if history:
        for msg in history[-10:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
    return messages
