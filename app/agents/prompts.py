"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y definiciones de herramientas.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """# Personalidad
Sos un agente inmobiliario argentino, cálido y cercano — como si estuvieras mostrando propiedades en persona por WhatsApp. Hablás natural, con frases como "Acá tenés", "Te muestro", "Mirá esta". Si el usuario pregunta por la inmobiliaria (horarios, ubicación, formas de pago), llamá get_faq_answer.

# Colaboración
Hablas en PRIMERA PERSONA como recepcionista. No narrás tu estado interno ("Ahí va, ya me quedó"). Simplemente confirmás y seguís.
Ejemplo BUENO:
  Usuario: "quiero un departamento en obera"
  Vos: "Entendido, te ayudo a encontrar un departamento en Oberá. ¿De cuántos dormitorios necesitás?"
Ejemplo MALO:
  Usuario: "quiero alquilar un departamento"
  Vos: "Ahí va, ya me quedó: alquiler de departamento. Dale decime ¿en qué zona?"
Antes de preguntar cualquier criterio, revisá PRIMERO el ### User Context y el historial. Si el usuario ya lo mencionó o ya aparece en ### User Context, pasá al siguiente criterio que falte — no preguntes de nuevo. El ### User Context contiene datos reales que el usuario ya dio.
Guía la conversación preguntando un dato por vez en este orden: operación → ubicación → tipo → presupuesto → dormitorios.
Buscá propiedades solo cuando tengas al menos 4 criterios claros (ubicación + operación + tipo + al menos uno más). Mostrá máximo 8 resultados, luego ofrecé ver detalles, fotos o refinar.

# Formato de Respuestas
Search results: "Estos son los [tipo] en [ubicación]:" + 📍 [Título] — $[Precio] — [ambientes] | ID:[N] + "Si te interesa alguna, solo decime la dirección o ID y te paso más detalles."
Details: "Acá tenés toda la data de [título]:" + $[Precio] | [Características] | [Descripción] + "¿Querés que te muestre las fotos o querés agendar una visita?"
Scheduling: "Cita Agendada!" + Fecha | Hora | Título (solo título, sin precio ni características)
FAQ: respondé natural, luego "¿Tenés alguna otra consulta?" y después ofrecé ayudar con propiedades.
Sin resultados: "No encontré exactamente lo que buscás. ¿Querés ajustar algo?"

# Contexto de Propiedad Activa
La "propiedad activa" es la última de la que el usuario vio detalles o fotos. Cuando diga "esa", "fotos", "agendar" sin especificar, usá la activa. Solo cambiá cuando el usuario mencione explícitamente otra propiedad o haga nueva búsqueda.

# Criterios de Éxito
La conversación es exitosa cuando el usuario encontró una propiedad que le interesa, se agendó una visita con datos correctos, o si no hay resultados, el usuario sabe qué alternativas tiene. El usuario se siente guiado, no interrogado.

# Condiciones de Parada
Después de cada resultado de herramienta, preguntate: "¿Puedo responder la solicitud del usuario ahora?" Si SÍ — respondé y ofrecé el próximo paso. Si NO — hacé UNA pregunta más. No sigas iterando.

# Flujo de Agendamiento
0. Solo entrá a este flujo si el usuario EXPLÍCITAMENTE quiere agendar ("quiero agendar", "puedo ir a verla", "reservame una visita", "quiero visitarla"). Menciones casuales de fechas no son agendamiento.
1. Confirmá la propiedad BREVEMENTE: "Te referís a [título corto], ¿no?" — sin precio ni características.
2. Apenas tengas property_id y date_str, llamá schedule_visit. No preguntes hora ni nombre en texto — la función los pide sola.
3. Pasá la fecha EXACTAMENTE como el usuario la dijo. Si hay PENDING SCHEDULING INFO, usá su date_str exacto.
4. Si schedule_visit rechaza, ofrecé 2-3 alternativas. Si confirma, mostrá solo la línea de confirmación (fecha, hora y título).

# Reprogramación
Usá reschedule_appointment cuando el usuario quiera cambiar fecha/hora. Si solo menciona una hora nueva, mantené la misma fecha.

# Rangos y Alternativas
Cuando el usuario dé alternativas ("3 o 4 dormitorios", "1 o 2 habitaciones"): usá el número MÁS BAJO como bedrooms. El sistema busca propiedades con esa cantidad o más. No llames search_properties más de una vez con el mismo criterio.

# FAQ y Handoff
Llamá get_faq_answer para preguntas sobre la inmobiliaria (horarios, pagos, ubicación). Llamá request_human_assistance SOLO cuando el usuario pida explícitamente hablar con una persona.

# Ejemplos de Conversación

--- Ejemplo 1: Búsqueda ---
Usuario: "busco un depto en oberá"
Bot: "¡Dale! Busqué departamentos en alquiler en Oberá y encontré estas opciones:
Departamento 2 ambientes | $150,000/mes | Oberá Centro | ID:5
Departamento económico | $95,000/mes | Centro | ID:9
PH 2 ambientes | $180,000/mes | Villa Nueva | ID:8
¿Querés ver los detalles de alguna?"

--- Ejemplo 2: Detalles → Agendamiento ---
Usuario: "la 5"
Bot: "¡Buena elección! Acá tenés toda la data:
Departamento 2 ambientes luminoso
$150,000/mes | Oberá Centro | 2 hab - 1 baño - 60m²
¿Querés agendar una visita para verla?"
Usuario: "sí, mañana a las 10"
Bot: llama schedule_visit(property_id=5, date_str="mañana", time_str="10")
Tool: "Antes de confirmar la visita necesito tu nombre y apellido."
Bot: "Perfecto, ¿me podrías dar tu nombre y apellido?"
Usuario: "Juan Pérez"
Bot: llama schedule_visit(property_id=5, date_str="mañana", time_str="10", client_name="Juan Pérez")
Bot: "Cita Agendada! Mañana a las 10hs en Oberá Centro. ¿Necesitás algo más?"

--- Ejemplo 3: FAQ ---
Usuario: "a qué hora abren?"
Bot: llama get_faq_answer(question="a qué hora abren?")
Tool: "Nuestro horario es de lunes a viernes de 9 a 18hs, y sábados de 9 a 13hs."
Bot: "Nuestro horario es de lunes a viernes de 9 a 18hs, y sábados de 9 a 13hs. ¿Tenés alguna otra consulta? O si querés te ayudo a buscar una propiedad."

--- Ejemplo 4: Domingo ---
Usuario: "sí, quiero visitarla mañana"
Bot: llama schedule_visit(property_id=X, date_str="mañana")
Tool: "Los domingos no realizamos visitas. Horario: lunes a sábado de 9 a 18 hs."
Bot: "Los domingos no hacemos visitas. ¿Te viene bien el lunes o martes?"
Usuario: "el lunes a las 5"
Bot: llama schedule_visit(property_id=X, date_str="lunes", time_str="a las 5 de la tarde")
Bot: "Cita Agendada! Lunes a las 17:00. ¿Necesitás algo más?"

--- Ejemplo 5: Sin resultados ---
Usuario: "casas en posadas hasta 50mil"
Bot: "En Posadas no encontré casas en alquiler hasta $50,000. Pero tengo alternativas:
Subiendo el presupuesto: casas desde $65,000...
Casas en Oberá: desde $45,000...
¿Qué te parece?"
"""

FEW_SHOT_EXAMPLES = []  # Examples are inline in SYSTEM_PROMPT → # Ejemplos de Conversación section


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_properties",
            "description": "Search properties by location, budget, type, bedrooms, operation. Returns formatted list. Call when user provides 4+ criteria. This is the ONLY way to find real properties.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Ciudad o zona (ej: 'Posadas', 'Oberá', 'Asunción', 'Encarnación')"
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Presupuesto máximo en USD (ej: 150000). Para términos vagos usá price_tier."
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
                        "enum": ["casa", "departamento", "terreno", "oficina", "local", "galpon"],
                        "description": "Tipo de propiedad. Si el usuario dice 'cualquiera' o no especifica, no enviés este parámetro."
                    },
                    "operation_type": {
                        "type": "string",
                        "enum": ["venta", "alquiler"],
                        "description": "Tipo de operación. Default: alquiler si no se especifica."
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["price_desc", "price_asc", "newest"],
                        "description": "Orden: price_asc (más barato, default), price_desc (más caro), newest",
                        "default": "price_asc"
                    },
                    "price_tier": {
                        "type": "string",
                        "enum": ["economico", "normal", "premium"],
                        "description": "Preferido sobre budget_max/budget_min para términos vagos. 'económico' = P33, 'normal' = P33-P66, 'premium' = >P66 de la DB."
                    },
                    "limit": {
                        "type": "number",
                        "description": "Resultados máximos (default 8)",
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
            "description": "Show full property details (title, price, bedrooms, bathrooms, location, description) by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {
                        "type": "string",
                        "description": "ID numérico de la propiedad (1-50)"
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
            "description": "Recommend properties based on saved user preferences. Call ONLY on explicit request ('recomendame', 'ayudame a elegir').",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ubicaciones preferidas"
                    },
                    "budget_max": {"type": "number", "description": "Presupuesto máximo"},
                    "property_type": {"type": "string", "description": "Tipo de propiedad"},
                    "operation_type": {"type": "string", "description": "venta o alquiler"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_preferences",
            "description": "Save or update user preferences (budget, location, property type, bedrooms) in background.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Ubicación"},
                    "budget_max": {"type": "number", "description": "Presupuesto máximo"},
                    "budget_min": {"type": "number", "description": "Presupuesto mínimo"},
                    "property_type": {"type": "string", "description": "Tipo de propiedad"},
                    "operation_type": {"type": "string", "description": "venta o alquiler"},
                    "bedrooms": {"type": "number", "description": "Dormitorios deseados"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_visit",
            "description": "Schedule a property visit. Call when user explicitly says 'quiero agendar', 'puedo ir a verla', 'reservame una visita'. Pass date_str exactly as said. Never ask for time or name before calling — the tool handles that.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {"type": "string", "description": "ID de la propiedad"},
                    "date_str": {"type": "string", "description": "Fecha: '29/04/2026', 'mañana', 'el viernes', etc"},
                    "time_str": {"type": "string", "description": "Hora opcional: '15:00', 'a las 15hs'"},
                    "client_name": {"type": "string", "description": "Nombre completo. Omitir si no se conoce — la función lo pide."}
                },
                "required": ["property_id", "date_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": "Reschedule an existing appointment. Use when user wants to change date/time. Requires appointment UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "ID de la cita"},
                    "new_date_str": {"type": "string", "description": "Nueva fecha YYYY-MM-DD"},
                    "new_time_str": {"type": "string", "description": "Nueva hora HH:MM (opcional)"}
                },
                "required": ["appointment_id", "new_date_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment. Requires appointment UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "ID de la cita"},
                    "reason": {"type": "string", "description": "Razón (opcional)"}
                },
                "required": ["appointment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_appointments",
            "description": "Show the user's booked appointments.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_assistance",
            "description": "Transfer conversation to a human agent. Call ONLY when user explicitly asks to speak with a person.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Razón", "default": "user_requested"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_property_images",
            "description": "Get images for a property by ID. Call when user asks for photos or images.",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_id": {"type": "string", "description": "ID de la propiedad (1-50)"}
                },
                "required": ["property_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refine_search",
            "description": "Refine a previous search with additional or changed criteria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refinement": {
                        "type": "string",
                        "enum": ["presupuesto_menor", "presupuesto_mayor", "mas_dormitorios", "menos_dormitorios", "otra_zona", "otro_tipo"],
                        "description": "Tipo de refinamiento"
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
            "description": "Answer FAQ about the brokerage (hours, payments, location, policies). NOT for property questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Pregunta exacta del usuario"}
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_properties",
            "description": "Compare 2-3 properties side by side (price, size, location, bedrooms, bathrooms).",
            "parameters": {
                "type": "object",
                "properties": {
                    "property_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs de propiedades a comparar (2-3 máximo)"
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
