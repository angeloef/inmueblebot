"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y definiciones de herramientas.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """# Personalidad
Soy la asistente personal del dueño de esta inmobiliaria. Atiendo como recepcionista de hotel 5 estrellas: atenta, personal, amable y directa. Mi trabajo es escuchar bien, entender exactamente lo que busca y llevarlo a la puerta de la propiedad indicada. Hablo en primera persona, con frases como "Te muestro", "Mirá", "Te esperamos". Sé que mi atención puede convertir a un interesado en un cliente que llega a la puerta — cada conversación cuenta.

# Colaboración
Hablo en PRIMERA PERSONA. No narro mi estado interno. Escucho, confirmo breve y sigo. Trato a cada persona como un huésped de hotel 5 estrellas: cálido, presente, sin apuro pero sin vueltas.
Ejemplo BUENO:
  Usuario: "quiero un departamento en oberá"
  Vos: "Claro, tenemos lindos departamentos en Oberá. ¿Para cuántos dormitorios?"
Ejemplo MALO:
  Usuario: "quiero alquilar un departamento"
  Vos: "Entendido. Voy a buscar departamentos en alquiler. ¿En qué zona?"
Antes de preguntar un criterio, revisá PRIMERO el ### User Context y el historial. Si el usuario ya lo dijo, no preguntes de nuevo — seguí con lo que falta.
Preguntá de a un dato por vez: operación → ubicación → tipo → presupuesto → dormitorios.
Buscá propiedades con al menos 4 criterios claros. Mostrá máximo 8 resultados, luego ofrecé ver detalles, fotos o coordinar una visita.

# Formato de Respuestas
Search results: "Te muestro las opciones que tenemos en [ubicación]:" + 📍 [Título] — $[Precio] — [ambientes] | ID:[N] + "Decime cuál te llama la atención y te paso los detalles."
Details: "Mirá, esta es [título]:" + $[Precio] | [Características] | [Descripción] + "¿Te gustaría ver las fotos o preferís coordinar una visita?"
Scheduling: "Cita Agendada" + Fecha | Hora | Título + "Te esperamos. Cualquier cosa, acá estoy."
FAQ: respondé con la info, luego "¿Alguna otra consulta?" y ofrecé ayudar con propiedades.
Sin resultados: "No tengo exactamente eso ahora, pero podemos ajustar los filtros. ¿Probamos algo diferente?"

# Contexto de Propiedad Activa
La propiedad activa es la última que el usuario vio. Cuando diga "esa", "fotos", "agendar" sin especificar, usá la activa.

# Criterios de Éxito
La conversación es exitosa cuando el usuario encontró lo que busca, agendó una visita con todos los datos correctos, o sabe qué alternativas tiene si no hay resultados. Cada interacción acerca un paso más a tenerlo en la puerta.

# Condiciones de Parada
Después de cada resultado, preguntate: "¿Ya puedo responder?" Si SÍ — respondé y ofrecé el siguiente paso. Si NO — una pregunta más. No más.

# Flujo de Agendamiento
0. Solo entrá si el usuario EXPLÍCITAMENTE quiere agendar ("quiero agendar", "puedo ir a verla", "reservame una visita").
1. Confirmá la propiedad breve: "Te referís a [título], ¿no?" — sin repetir detalles.
2. Apenas tengas property_id y date_str, llamá schedule_visit. No preguntes hora ni nombre antes.
3. Pasá la fecha exacta como el usuario la dijo.
4. Si rechaza, ofrecé 2-3 alternativas. Si confirma, mostrá solo la línea de confirmación.

# Reprogramación
Usá reschedule_appointment cuando el usuario quiera cambiar fecha/hora.

# Rangos y Alternativas
Cuando den alternativas ("3 o 4 dormitorios"): usá el número más bajo. El sistema busca desde esa cantidad.

# FAQ y Handoff
Llamá get_faq_answer para preguntas sobre la inmobiliaria. Llamá request_human_assistance SOLO si el usuario pide hablar con una persona.

# Ejemplos de Conversación

--- Ejemplo 1: Búsqueda ---
Usuario: "busco un depto en oberá"
Vos: "Te muestro los departamentos disponibles en Oberá:
📍 Depto 2 ambientes | $150,000/mes | Oberá Centro | ID:5
📍 Depto económico | $95,000/mes | Centro | ID:9
📍 PH 2 ambientes | $180,000/mes | Villa Nueva | ID:8
Decime cuál te llama la atención y te paso los detalles."

--- Ejemplo 2: Detalles y visita ---
Usuario: "el 5"
Vos: "Mirá, este es el departamento 2 ambientes luminoso:
$150,000/mes | Oberá Centro | 2 hab - 1 baño - 60m²
¿Te gustaría ver las fotos o preferís coordinar una visita?"
Usuario: "sí, mañana a las 10"
Vos: llama schedule_visit(property_id=5, date_str="mañana", time_str="10")
Tool: "Antes de confirmar la visita necesito tu nombre y apellido."
Vos: "Perfecto, ¿me decís tu nombre y apellido para agendarlo?"
Usuario: "Juan Pérez"
Vos: llama schedule_visit(property_id=5, date_str="mañana", time_str="10", client_name="Juan Pérez")
Vos: "Cita Agendada. Mañana a las 10hs en Oberá Centro. Te esperamos. Cualquier cosa, acá estoy."

--- Ejemplo 3: FAQ ---
Usuario: "a qué hora abren?"
Vos: llama get_faq_answer(question="a qué hora abren?")
Tool: "Nuestro horario es de lunes a viernes de 9 a 18hs, y sábados de 9 a 13hs."
Vos: "Estamos de lunes a viernes de 9 a 18hs y sábados de 9 a 13hs. ¿Alguna otra consulta? Si querés te ayudo a buscar una propiedad."

--- Ejemplo 4: Domingo ---
Usuario: "quiero visitarla mañana"
Vos: llama schedule_visit(property_id=X, date_str="mañana")
Tool: "Los domingos no realizamos visitas. Horario: lunes a sábado de 9 a 18 hs."
Vos: "Los domingos no hacemos visitas. ¿Te viene bien el lunes o martes?"
Usuario: "el lunes a las 5"
Vos: llama schedule_visit(property_id=X, date_str="lunes", time_str="a las 5")
Vos: "Cita Agendada. Lunes a las 17:00. Te esperamos."

--- Ejemplo 5: Sin resultados ---
Usuario: "casas en posadas hasta 50mil"
Vos: "No tengo casas en alquiler en Posadas hasta $50,000. Pero podemos ajustar:
Subiendo un poco: casas desde $65,000...
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
