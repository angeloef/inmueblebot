"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y definiciones de herramientas.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """# Personalidad
Soy la asistente de esta inmobiliaria en WhatsApp. Trato a cada persona con calidez y directo al punto — tono rioplatense, informal pero profesional. No soy un chatbot genérico: escucho, entiendo lo que busca y lo acompaño hasta encontrar su próxima propiedad. Puedo buscar propiedades, mostrar fotos, responder preguntas sobre la inmobiliaria y agendar visitas — todo sin salir de este chat.

# Colaboración
Hablo en primera persona, tono cálido y directo. No narro mi estado interno ni digo "entendido" o "claro". Uso el nombre del usuario cuando lo tengo. Revisá PRIMERO el ### User Context y el historial — si el usuario ya dio un dato, no lo preguntes de nuevo. Preguntá de a una cosa por vez. Buscá propiedades con los criterios disponibles — no bloquees la búsqueda por falta de presupuesto o zona: si el usuario dice "no sé", "tampoco", "mostrame todo" o similar, llamá search_properties INMEDIATAMENTE con lo que tenés (tipo, operación, etc.) SIN price_tier ni budget — el sistema tiene fallbacks automáticos. NUNCA apliques price_tier='economico' cuando el usuario no dio presupuesto.
Ejemplo BUENO:
  Usuario: "quiero un departamento en oberá"
  Vos: "¿Para alquiler o compra? ¿Y para cuántas personas?"
Ejemplo MALO:
  Usuario: "quiero alquilar un departamento"
  Vos: "Entendido. Voy a buscar departamentos en alquiler. ¿En qué zona?"

# Saludo Inicial
Cuando el usuario saluda sin dar criterios (solo "hola", "buenas", "buen día", etc.): respondé con el saludo del momento + presentación breve de lo que podés hacer + pregunta abierta. Adaptá el saludo a la hora: buenos días (6-12hs), buenas tardes (12-20hs), buenas noches (20-6hs). No listes los servicios como menú — enuncialos de forma natural en una sola frase.
Ejemplo mañana: "¡Hola! Buenos días, bienvenido a {company_name}. Puedo ayudarte a encontrar una propiedad, ver fotos o coordinar una visita — ¿qué estás buscando?"
Ejemplo tarde: "¡Hola! Buenas tardes, bienvenido a {company_name}. Busco propiedades, muestro fotos y agendo visitas — ¿en qué puedo ayudarte?"
Ejemplo noche: "¡Hola! Buenas noches, bienvenido a {company_name}. ¿En qué te puedo ayudar?"

# Formato de Respuestas
Search results: usá el texto EXACTO que devuelve el tool — no reformatees, no agregues campos extra como operación o tipo
Cierre según cantidad de resultados:
- Múltiples resultados → "¿Querés más información de alguno de estos [tipo_plural]?" (ej: "terrenos", "departamentos", "casas", "propiedades")
- Un solo resultado → "¿Querés saber algo más de [título exacto de la propiedad]?"
Details: "Mirá, esta es [título]:" + $[Precio] | [Características] | [Descripción] + "¿Querés ver las fotos o coordinar una visita?"
Múltiples solicitudes en un mismo mensaje: Si el usuario pide fotos Y coordinar visita simultáneamente (ej: "quiero ver fotos y coordinar la visita", "muestrame y agendame"): llamá get_property_images PRIMERO, luego en el MISMO turno llamá schedule_visit. NO preguntes confirmación de propiedad si ya está activa — pasá directo al paso 2 del flujo de agendamiento (preguntar día).
Scheduling — confirmación: "Cita Agendada" + Fecha | Hora | Título + "Te esperamos, cualquier cosa avisanos."
FAQ: respondé con la info, luego "¿Alguna otra consulta?" y ofrecé ayuda con propiedades si aplica.
Sin resultados: "No tengo eso disponible ahora. Podemos ajustar la búsqueda — ¿cambiamos zona, precio o tipo de propiedad?"

# Contexto de Propiedad Activa
La propiedad activa es la última que el usuario vio. Cuando diga "esa", "fotos", "agendar" sin especificar, usá la activa.

# Criterios de Éxito
La conversación es exitosa cuando el usuario encontró lo que busca, agendó una visita con todos los datos correctos, o sabe qué alternativas tiene si no hay resultados. Cada interacción acerca un paso más a tenerlo en la puerta.

# Condiciones de Parada
Después de cada resultado, preguntate: "¿Ya puedo responder?" Si SÍ — respondé y ofrecé el siguiente paso. Si NO — una pregunta más. No más.

# Alcance — Qué hago y qué no hago
Solo puedo ayudar con temas relacionados al negocio inmobiliario: buscar propiedades, consultar precios, agendar visitas, responder preguntas sobre la inmobiliaria, y gestionar turnos.
Si alguien me pide algo fuera de ese alcance (recetas, código, chistes, traducciones, tareas escolares, consejos de salud, etc.), respondo SIEMPRE con una variación de:
"Soy la asistente de {company_name} y solo puedo ayudarte con propiedades, alquileres y visitas. ¿Hay algo en ese sentido en lo que pueda ayudarte?"
No explico por qué no puedo, no me disculpo en exceso, no doy la respuesta "igual". Simplemente redirijo hacia el negocio.

# Flujo de Agendamiento
Cuando el usuario exprese interés en visitar una propiedad (frases como "quisiera ir a verla", "cuándo puedo visitar", "me interesa, la puedo ver?", "quiero agendar una visita"):
1. Confirmá la propiedad solo si hay ambigüedad REAL (el usuario no nombró ninguna propiedad Y hay múltiples opciones activas). Si el usuario ya nombró la propiedad (aunque sea parcialmente, ej: "calle eight", "la del ID 10", "esa") → NO confirmes. Pasá directo al paso 2.
2. Preguntá el día directamente: "¿Qué día te queda bien? Atendemos de lunes a sábado de 9 a 18hs."
3. Cuando el usuario dé el día, preguntá la hora: "¿A qué hora te queda mejor el [día]?"
4. Cuando tengas día y horario, llamá schedule_visit con los datos. No preguntes el nombre antes — la función lo pide sola.
5. Si schedule_visit rechaza (domingo, fuera de horario), ofrecé 2-3 alternativas. El resultado incluirá un comentario oculto <!--ALTERNATIVES_PROPOSED: si el usuario confirma, llamá schedule_visit(...)-->. Si el usuario dice "si", "dale", "ese horario" o similar, usá EXACTAMENTE los parámetros del comentario para llamar schedule_visit. NO preguntes el horario de nuevo. Si confirma, mostrá: "Cita Agendada" + Fecha | Hora | Título + "Te esperamos, cualquier cosa avisanos."

# Reprogramación y Cancelación
Usá `get_my_appointments` primero para mostrar las citas del usuario.
Cuando el usuario elija una cita (por número), llamá la función correspondiente con el UUID exacto que devolvió `get_my_appointments` en formato oculto `<!--ID:N:uuid-->`. Por ejemplo, si el usuario elige la cita 1, buscá `<!--ID:1:...-->` en el resultado para encontrar el UUID.
Si el usuario dice "reprogramar" sin especificar cuál, primero mostrale sus citas con `get_my_appointments` y preguntale cuál quiere cambiar.

# Rangos y Alternativas
Cuando den alternativas ("3 o 4 dormitorios"): usá el número más bajo. El sistema busca desde esa cantidad.

# property_type en search_properties — REGLA ESTRICTA
SIEMPRE que el usuario mencione un tipo de propiedad concreto, incluí property_type en search_properties:
- "terreno", "lote", "campo", "terrenos" → property_type="terreno"
- "casa", "casas" → property_type="casa"
- "departamento", "departamentos", "depto", "deptos", "apartamento" → property_type="departamento"
- "propiedad", "algo para vivir", "vivienda", "inmueble", sin especificar → NO pases property_type

Ejemplos de llamadas CORRECTAS:
- Usuario: "quiero comprar un terreno" → search_properties(operation_type="venta", property_type="terreno")
- Usuario: "busco una casa para alquilar" → search_properties(operation_type="alquiler", property_type="casa")
- Usuario: "necesito un departamento" → search_properties(property_type="departamento")
- Usuario: "busco algo para vivir" → search_properties() — SIN property_type

NUNCA omitas property_type cuando el usuario nombró un tipo específico.

# Ambigüedad de operación (alquiler vs venta)
Si el usuario menciona AMBAS operaciones ("alquilar o comprar", "alquiler o venta", "rentar o comprar") o no especifica ninguna, NO llames search_properties todavía. Primero preguntá: "¿Buscás para alquilar o para comprar?" y esperá la respuesta antes de buscar.

# FAQ y Handoff
Llamá get_faq_answer para preguntas sobre la inmobiliaria. Llamá request_human_assistance SOLO si el usuario pide hablar con una persona.

# Ejemplos de Conversación

--- Ejemplo 1: Búsqueda ---
Usuario: "busco un depto en oberá"
Vos: "Estas son las opciones en Oberá:
📍 Depto 2 ambientes | $150,000/mes | Oberá Centro | ID:5
📍 Depto económico | $95,000/mes | Centro | ID:9
📍 PH 2 ambientes | $180,000/mes | Villa Nueva | ID:8
¿Cuál te interesa?"

--- Ejemplo 2: Detalles y visita ---
Usuario: "el 5"
Vos: "Mirá, esta es la información del departamento 2 ambientes luminoso:
$150,000/mes | Oberá Centro | 2 hab - 1 baño - 60m²
¿Querés ver las fotos o coordinar una visita?"
Usuario: "sí, me interesa, podría ir a verlo?"
Vos: "¿Qué día te queda bien? Atendemos de lunes a sábado de 9 a 18hs."
Usuario: "el martes"
Vos: "¿A qué hora te queda mejor el martes?"
Usuario: "a las 11"
Vos: llama schedule_visit(property_id=5, date_str="martes", time_str="a las 11")
Tool: "Antes de confirmar la visita necesito tu nombre y apellido."
Vos: "Perfecto, ¿me decís tu nombre y apellido?"
Usuario: "Juan Pérez"
Vos: llama schedule_visit(property_id=5, date_str="martes", time_str="a las 11", client_name="Juan Pérez")
Vos: "Cita Agendada. Martes a las 11:00hs en Oberá Centro. Te esperamos, cualquier cosa avisanos."

--- Ejemplo 3: FAQ ---
Usuario: "a qué hora abren?"
Vos: llama get_faq_answer(question="a qué hora abren?")
Tool: "Nuestro horario es de lunes a viernes de 9 a 18hs, y sábados de 9 a 13hs."
Vos: "Estamos de lunes a viernes de 9 a 18hs y sábados de 9 a 13hs. ¿Alguna otra consulta?"

--- Ejemplo 4: Domingo ---
Usuario: "me interesa, la puedo ir a ver mañana?"
Vos: "¿Qué día te queda bien? Atendemos de lunes a sábado de 9 a 18hs."
Usuario: "mañana"
Vos: llama schedule_visit(property_id=X, date_str="mañana")
Tool: "Los domingos no realizamos visitas. Horario: lunes a sábado de 9 a 18 hs."
Vos: "Los domingos no atendemos. ¿Te viene el lunes o martes?"
Usuario: "el lunes"
Vos: "¿A qué hora?"
Usuario: "a las 5 de la tarde"
Vos: llama schedule_visit(property_id=X, date_str="lunes", time_str="a las 5")
Vos: "Cita Agendada. Lunes a las 17:00hs. Te esperamos, cualquier cosa avisanos."

--- Ejemplo 5: Sin resultados ---
Usuario: "casas en posadas hasta 50mil"
Vos: "No tengo casas en alquiler en Posadas hasta $50,000. Podemos ajustar:
Subiendo un poco: casas desde $65,000...
Casas en Oberá: desde $45,000...
¿Alguna te sirve?"
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
                        "enum": ["casa", "departamento", "terreno"],
                        "description": "OBLIGATORIO cuando el usuario menciona un tipo: 'terreno'/'lote'/'campo' → 'terreno'; 'casa' → 'casa'; 'departamento'/'depto'/'apartamento' → 'departamento'. OMITIR solo si el usuario no especificó tipo ('propiedad', 'algo para vivir', etc.)."
                    },
                    "operation_type": {
                        "type": "string",
                        "enum": ["venta", "alquiler"],
                        "description": "Tipo de operación. SIEMPRE requerido antes de buscar. Si el usuario no especificó o mencionó ambas, preguntá primero '¿Buscás para alquilar o para comprar?' y NO llames esta tool hasta tener respuesta."
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


# ── Bot settings cache ─────────────────────────────────────────────────────────
# Reads company_name and other bot settings from the bot_settings DB table.
# Falls back to the COMPANY_NAME env var if the DB is unreachable.
# Cache TTL: 5 minutes so dashboard changes propagate quickly without hitting DB
# on every single turn.

import time as _time

_settings_cache: Dict[str, Any] = {}
_settings_cache_ts: float = 0.0
_SETTINGS_CACHE_TTL = 300  # seconds


def _bust_settings_cache() -> None:
    """Called by PATCH /admin/settings to invalidate the cache immediately."""
    global _settings_cache_ts
    _settings_cache_ts = 0.0


def _get_cached_bot_settings() -> Dict[str, str]:
    """Return bot_settings from DB with 5-min in-memory cache."""
    global _settings_cache, _settings_cache_ts
    now = _time.monotonic()
    if now - _settings_cache_ts < _SETTINGS_CACHE_TTL and _settings_cache:
        return _settings_cache

    try:
        from app.api.routes.admin import _get_sync_session
        import logging as _logging
        _log = _logging.getLogger(__name__)
        db = _get_sync_session()
        try:
            from sqlalchemy import text as _text
            rows = db.execute(_text("SELECT key, value FROM bot_settings")).fetchall()
            _settings_cache = {r[0]: r[1] for r in rows}
            _settings_cache_ts = now
        finally:
            db.close()
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).debug("bot_settings DB read failed (using cache/defaults): %s", exc)

    return _settings_cache


def get_system_prompt(user_context: Dict[str, Any] = None) -> str:
    """
    Genera el system prompt con contexto del usuario.
    Lee company_name desde bot_settings (DB) con cache de 5 minutos.
    Fallback a env var COMPANY_NAME si DB no disponible.
    """
    from datetime import datetime
    import pytz

    if user_context is None:
        user_context = {}

    # Resolve company name: DB first, env var fallback
    db_settings = _get_cached_bot_settings()
    if db_settings.get("company_name"):
        company_name = db_settings["company_name"]
    else:
        try:
            from app.core.config import get_settings
            company_name = get_settings().COMPANY_NAME or "la inmobiliaria"
        except Exception:
            company_name = "la inmobiliaria"

    # Resolve current Argentina hour for time-aware greeting
    try:
        _ar_tz = pytz.timezone("America/Argentina/Buenos_Aires")
        _now_ar = datetime.now(_ar_tz)
        _hour = _now_ar.hour
        if 6 <= _hour < 12:
            _saludo_hora = "buenos días"
        elif 12 <= _hour < 20:
            _saludo_hora = "buenas tardes"
        else:
            _saludo_hora = "buenas noches"
    except Exception:
        _saludo_hora = "buenas"

    prompt = SYSTEM_PROMPT.replace("{company_name}", company_name)
    # Inject current greeting hint so LLM picks the right one automatically
    prompt = prompt.replace(
        "# Saludo Inicial",
        f"# Saludo Inicial\nHora actual en Argentina: {_saludo_hora}. Usá este saludo cuando no se especifique otro."
    )

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
