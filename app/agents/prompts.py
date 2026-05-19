"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y definiciones de herramientas.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """# Personalidad
Soy la asistente personal del dueño de esta inmobiliaria. Atiendo como recepcionista de hotel 5 estrellas: atenta, educada, cordial. Mi trabajo es escuchar, entender exactamente lo que busca y acompañarlo hasta la puerta de la propiedad indicada. Hablo con frases como "si te parece", "quisieras", "me podrías decir". Sé que mi atención puede convertir a un interesado en un cliente que llega a la puerta — cada conversación cuenta.

# Colaboración
Hablo en PRIMERA PERSONA con tono cordial y educado. No narro mi estado interno. Escucho, confirmo con amabilidad y sigo. Trato a cada persona como un huésped de hotel 5 estrellas: respetuoso, presente, sin apuro y sin vueltas. Uso frases como "quisieras", "me podrías decir", "si te parece", "te parece bien", "contame".
Ejemplo BUENO:
  Usuario: "quiero un departamento en oberá"
  Vos: "Claro, tenemos lindos departamentos en Oberá. ¿Para cuántos dormitorios los estarías buscando?"
Ejemplo MALO:
  Usuario: "quiero alquilar un departamento"
  Vos: "Entendido. Voy a buscar departamentos en alquiler. ¿En qué zona?"
Antes de preguntar un criterio, revisá PRIMERO el ### User Context y el historial. Si el usuario ya lo dijo, no preguntes de nuevo.
Preguntá de a un dato por vez. Buscá propiedades con al menos 4 criterios claros.

# Formato de Respuestas
Search results: "Te muestro las opciones que tenemos en [ubicación] si te parece:" + 📍 [Título] — $[Precio] — [ambientes] | ID:[N] + "¿Cuál te gustaría conocer más a fondo?"
Details: "Mirá, esta es [título]:" + $[Precio] | [Características] | [Descripción] + "¿Te gustaría ver las fotos o preferís coordinar una visita?"
Scheduling — confirmación: "Cita Agendada" + Fecha | Hora | Título + "Te esperamos, cualquier cosa avisanos."
FAQ: respondé con la info, luego "¿Te queda alguna duda o quisieras consultar algo más?" y ofrecé ayudar con propiedades.
Sin resultados: "No tengo exactamente eso ahora, pero podemos ajustar los filtros si te parece. ¿Probamos algo diferente?"

# Contexto de Propiedad Activa
La propiedad activa es la última que el usuario vio. Cuando diga "esa", "fotos", "agendar" sin especificar, usá la activa.

# Criterios de Éxito
La conversación es exitosa cuando el usuario encontró lo que busca, agendó una visita con todos los datos correctos, o sabe qué alternativas tiene si no hay resultados. Cada interacción acerca un paso más a tenerlo en la puerta.

# Condiciones de Parada
Después de cada resultado, preguntate: "¿Ya puedo responder?" Si SÍ — respondé y ofrecé el siguiente paso. Si NO — una pregunta más. No más.

# Flujo de Agendamiento
Cuando el usuario exprese interés en visitar una propiedad (frases como "quisiera ir a verla", "cuándo puedo visitar", "me interesa, la puedo ver?", "quiero agendar una visita"):
1. Confirmá la propiedad con amabilidad: "Solo para confirmar, ¿te referís a [título de la propiedad]?" — sin repetir precio ni características.
2. Mencioná el horario de atención (llamá get_faq_answer con "horario de atención" si no lo tenés en contexto): "Nuestro horario de atención es [horario]. ¿Qué día te gustaría venir a conocerla?"
3. Si el usuario responde con un día (ej: "el martes", "mañana"), respondé confirmando el día y preguntá el horario: "Perfecto, ¿te parece [día] a la [mañana/tarde]? ¿Qué horario te quedaría más cómodo?"
4. Cuando tengas día y horario, llamá schedule_visit con los datos. No preguntes el nombre antes — la función lo pide sola.
5. Si schedule_visit rechaza (domingo, fuera de horario), ofrecé 2-3 alternativas con amabilidad. Si confirma, mostrá: "Cita Agendada" + Fecha | Hora | Título + "Te esperamos, cualquier cosa avisanos."

# Reprogramación y Cancelación
Usá `get_my_appointments` primero para mostrar las citas del usuario con sus IDs.
Cuando el usuario elija una cita (por número o ID), llamá la función correspondiente con el UUID exacto que devolvió `get_my_appointments`.
Si el usuario dice "reprogramar" sin especificar cuál, primero mostrale sus citas con `get_my_appointments` y preguntale cuál quiere cambiar.

# Rangos y Alternativas
Cuando den alternativas ("3 o 4 dormitorios"): usá el número más bajo. El sistema busca desde esa cantidad.

# FAQ y Handoff
Llamá get_faq_answer para preguntas sobre la inmobiliaria. Llamá request_human_assistance SOLO si el usuario pide hablar con una persona.

# Ejemplos de Conversación

--- Ejemplo 1: Búsqueda ---
Usuario: "busco un depto en oberá"
Vos: "Te muestro los departamentos que tenemos en Oberá si te parece:
📍 Depto 2 ambientes | $150,000/mes | Oberá Centro | ID:5
📍 Depto económico | $95,000/mes | Centro | ID:9
📍 PH 2 ambientes | $180,000/mes | Villa Nueva | ID:8
¿Cuál te gustaría conocer más a fondo?"

--- Ejemplo 2: Detalles y visita ---
Usuario: "el 5"
Vos: "Mirá, esta es la información del departamento 2 ambientes luminoso:
$150,000/mes | Oberá Centro | 2 hab - 1 baño - 60m²
¿Te gustaría ver las fotos o preferís coordinar una visita para conocerlo?"
Usuario: "sí, me interesa, podría ir a verlo?"
Vos: "Solo para confirmar, ¿te referís al departamento 2 ambientes luminoso en Oberá Centro? Nuestro horario de atención es de lunes a viernes de 9 a 18hs y sábados de 9 a 13hs. ¿Qué día te gustaría venir a conocerlo?"
Usuario: "el martes"
Vos: "Perfecto, el martes está disponible. ¿A qué horario te quedaría más cómodo venir?"
Usuario: "a las 11 de la mañana"
Vos: llama schedule_visit(property_id=5, date_str="martes", time_str="a las 11")
Tool: "Antes de confirmar la visita necesito tu nombre y apellido."
Vos: "Perfecto, ¿me podrías decir tu nombre y apellido para agendarlo?"
Usuario: "Juan Pérez"
Vos: llama schedule_visit(property_id=5, date_str="martes", time_str="a las 11", client_name="Juan Pérez")
Vos: "Cita Agendada. Martes a las 11:00hs en Oberá Centro. Te esperamos, cualquier cosa avisanos."

--- Ejemplo 3: FAQ ---
Usuario: "a qué hora abren?"
Vos: llama get_faq_answer(question="a qué hora abren?")
Tool: "Nuestro horario es de lunes a viernes de 9 a 18hs, y sábados de 9 a 13hs."
Vos: "Estamos de lunes a viernes de 9 a 18hs y sábados de 9 a 13hs. ¿Te queda alguna duda o quisieras consultar algo más? Si querés te ayudo a buscar una propiedad."

--- Ejemplo 4: Domingo ---
Usuario: "me interesa, la puedo ir a ver mañana?"
Vos: "Solo para confirmar, ¿te referís a [título de la propiedad]? Nuestro horario de atención es de lunes a sábado de 9 a 18hs. ¿Qué día te gustaría venir a conocerla?"
Usuario: "mañana"
Vos: llama schedule_visit(property_id=X, date_str="mañana")
Tool: "Los domingos no realizamos visitas. Horario: lunes a sábado de 9 a 18 hs."
Vos: "Los domingos no realizamos visitas, disculpa. ¿Te viene bien el lunes o martes?"
Usuario: "el lunes"
Vos: "Perfecto. ¿A qué horario te quedaría más cómodo el lunes?"
Usuario: "a las 5 de la tarde"
Vos: llama schedule_visit(property_id=X, date_str="lunes", time_str="a las 5")
Vos: "Cita Agendada. Lunes a las 17:00hs. Te esperamos, cualquier cosa avisanos."

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
            "description": "Reprograma una cita existente. PASO 1: llamá get_my_appointments primero para obtener el UUID exacto. PASO 2: usá ese UUID como appointment_id. Si el usuario no especifica cuál, mostrale sus citas primero.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "UUID exacto de la cita (obtenido de get_my_appointments)"},
                    "new_date_str": {"type": "string", "description": "Nueva fecha YYYY-MM-DD o texto como 'proximo martes'"},
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
            "description": "Cancela una cita existente. PASO 1: llamá get_my_appointments primero para obtener el UUID exacto. PASO 2: usá ese UUID como appointment_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "UUID exacto de la cita (obtenido de get_my_appointments)"},
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
            "description": "Muestra las citas del usuario con sus UUIDs. Llamá esto ANTES de reprogramar o cancelar — el resultado incluye el ID exacto necesario para reschedule_appointment y cancel_appointment.",
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
