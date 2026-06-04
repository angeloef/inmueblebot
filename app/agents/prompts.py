"""
Prompts del agente de bienes raíces.
Incluye el system prompt principal y definiciones de herramientas.
"""
from typing import Dict, Any


SYSTEM_PROMPT = """# Personalidad
Soy la asistente de esta inmobiliaria en WhatsApp. Trato a cada persona con calidez y directo al punto — tono rioplatense, informal pero profesional. No soy un chatbot genérico: escucho, entiendo lo que busca y lo acompaño hasta encontrar su próxima propiedad. Puedo buscar propiedades, mostrar fotos, responder preguntas sobre la inmobiliaria y agendar visitas — todo sin salir de este chat.

# Colaboración
Hablo en primera persona, tono cálido y directo. No narro mi estado interno ni digo "entendido" o "claro". Uso el nombre del usuario cuando lo tengo. Revisá PRIMERO el ### User Context y el historial — si el usuario ya dio un dato, no lo preguntes de nuevo. Preguntá de a una cosa por vez. Reuní al menos 4 criterios claros (tipo + operación + zona + presupuesto o ambientes) antes de llamar search_properties. Si el usuario dice "no sé" o "mostrame todo" para un criterio, saltealo y buscá con lo que tengas si ya tenés 4 — no bloquees la búsqueda por falta de presupuesto o zona: si el usuario dice "no sé", "tampoco", "mostrame todo" o similar, llamá search_properties INMEDIATAMENTE con lo que tenés (tipo, operación, etc.) SIN price_tier ni budget — el sistema tiene fallbacks automáticos. NUNCA apliques price_tier='economico' cuando el usuario no dio presupuesto.
Ejemplo BUENO — usuario no especifica operación:
  Usuario: "quiero un departamento en oberá"
  Vos: "¿Para alquiler o compra? ¿Y para cuántas personas?"
Ejemplo BUENO — usuario YA especificó operación:
  Usuario: "alquilo un departamento"
  Vos: "¿Cuántas personas? ¿En qué zona?"
Ejemplo MALO:
  Usuario: "quiero alquilar un departamento"
  Vos: "Entendido. Voy a buscar departamentos en alquiler. ¿En qué zona?"

# Saludo Inicial
Usá esta sección SOLO si el usuario saluda sin dar criterios (solo "hola", "buenas", "buen día", etc.).
- Si el usuario YA dijo lo que busca (ej: "busco alquilar", "quiero un depto") → NO uses este saludo. Respondé directo sobre lo que pide.
- Si el usuario solo saludó: respondé con el saludo del momento + presentación breve de lo que podés hacer + pregunta abierta.
- Si el usuario saludó Y dió criterios (ej: "hola busco un depto") → respondé sobre los criterios, no te detengas en el saludo. Saludá rápido y seguí con la búsqueda. Adaptá el saludo a la hora: buenos días (6-12hs), buenas tardes (12-20hs), buenas noches (20-6hs). No listes los servicios como menú — enuncialos de forma natural en una sola frase.
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
Reglas para decidir si llamar search_properties o preguntar:
- Si el usuario dijo "alquilar", "alquiler", "alquilo", "rentar", "renta", "arrendar" → YA especificó alquiler. Pasá operation_type="alquiler". NO preguntes.
- Si el usuario dijo "comprar", "compra", "venta", "vender", "adquirir" → YA especificó compra/venta. Pasá operation_type="venta". NO preguntes.
- Si el usuario dijo AMBAS ("alquilar o comprar", "alquiler o venta") → preguntá primero.
- Si el usuario NO mencionó ninguna operación → preguntá primero.

# Resultados vacíos — señal NO_RESULTS_ASK_MORE
Si search_properties retorna exactamente "NO_RESULTS_ASK_MORE":
- NUNCA respondas con una lista vacía ni con "Estos son los X que tenemos disponibles:".
- Decí claramente que no hay propiedades disponibles con esos criterios.
- Ofrecé alternativas concretas: cambiar zona, ajustar presupuesto, otro tipo de operación.
- Ejemplo: "En este momento no tenemos casas disponibles en alquiler. ¿Te interesaría ver casas en venta, o buscamos en otra zona?"

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



# ── Sentiment / Urgency detection ──────────────────────────────────────────────

SENTIMENT_KEYWORDS = {
    "negative": [
        "no me gusta", "no sirve", "muy caro", "no me interesa",
        "qué mal", "que mal", "no gracias", "molesto", "aburrido",
        "no me convence", "no quiero", "no me sirve",
    ],
    "urgent": [
        "urgente", "necesito ya", "lo antes posible", "rapidísimo",
        "ya mismo", "necesito urgente",
    ],
}


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
                        "description": "Ciudad (ej: 'Posadas', 'Oberá', 'Asunción', 'Encarnación')"
                    },
                    "zone": {
                        "type": "string",
                        "description": "Zona o barrio específico (ej: 'Centro', 'Barrio Krause', 'Terminal'). Opcional — si no se especifica, busca en toda la ciudad indicada."
                    },
                    "budget_max": {
                        "type": "number",
                        "description": "Presupuesto máximo en ARS (pesos argentinos). Ej: 250000 para $250.000/mes"
                    },
                    "budget_min": {
                        "type": "number",
                        "description": "Presupuesto mínimo en ARS (pesos argentinos)"
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
                         "description": "Cantidad de resultados a devolver. DEFAULT 10. Pasá limit=10 siempre para mostrar el máximo de opciones. Si el usuario pide 'más opciones', llamá de nuevo con limit=10.",
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
    }
]


# ── Bot settings cache ─────────────────────────────────────────────────────────
# Reads company_name and other bot settings from the bot_settings DB table.
# Falls back to the COMPANY_NAME env var if the DB is unreachable.
# Cache TTL: 5 minutes so dashboard changes propagate quickly without hitting DB
# on every single turn.

import time as _time

# Tenant-keyed cache (V3 Phase 1): one entry per tenant so a rollback/flip on tenant A
# can't be masked by a stale global dict, and tenant B's overrides never bleed into A.
# Each value = global bot_settings (fallback) merged with that tenant's tenant_settings.
_settings_cache: Dict[str, Dict[str, str]] = {}
_settings_cache_ts: Dict[str, float] = {}
_SETTINGS_CACHE_TTL = 300  # seconds


def _bust_settings_cache() -> None:
    """Called by PATCH /admin/settings to invalidate the cache immediately (all tenants)."""
    _settings_cache.clear()
    _settings_cache_ts.clear()


def _get_cached_bot_settings() -> Dict[str, str]:
    """Return effective bot settings for the CURRENT tenant, with a 5-min in-memory cache.

    Resolution = global ``bot_settings`` (back-compat default for the existing single tenant)
    overlaid with this tenant's ``tenant_settings`` rows. For the default tenant with no
    overrides this is byte-identical to the old global behavior (V2 safe).
    """
    from app.core.tenancy import resolve_tenant_id
    tid = str(resolve_tenant_id())
    now = _time.monotonic()
    if now - _settings_cache_ts.get(tid, 0.0) < _SETTINGS_CACHE_TTL and tid in _settings_cache:
        return _settings_cache[tid]

    merged: Dict[str, str] = {}
    try:
        from app.api.routes.admin import _get_sync_session
        from sqlalchemy import text as _text
        db = _get_sync_session()
        try:
            rows = db.execute(_text("SELECT key, value FROM bot_settings")).fetchall()
            merged = {r[0]: r[1] for r in rows}
            # Per-tenant overrides (table may not exist pre-migration → guarded below).
            try:
                trows = db.execute(
                    _text("SELECT key, value FROM tenant_settings WHERE tenant_id = :tid"),
                    {"tid": tid},
                ).fetchall()
                for k, v in trows:
                    if v is not None:
                        merged[k] = v
            except Exception:
                pass  # tenant_settings not migrated yet — global values stand
            _settings_cache[tid] = merged
            _settings_cache_ts[tid] = now
        finally:
            db.close()
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).debug("bot_settings DB read failed (using cache/defaults): %s", exc)
        return _settings_cache.get(tid, {})

    return merged


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

# ── v2.0 State-specific prompts ──────────────────────────────────────────

def _sp(instructions):
    """Build a state prompt."""
    return _CORE_PERSONALITY + instructions + _STRUCTURED_OUTPUT_INSTRUCTION


_CORE_PERSONALITY = (
    "Soy la asistente de {company_name} en WhatsApp. "
    "Tono rioplatense, calido, directo, profesional. "
    'Hablo en primera persona. No narro mi estado interno ni digo "entendido" o "claro". '
    "Pregunto de a una cosa por vez. "
)

_STRUCTURED_OUTPUT_INSTRUCTION = (
    "RESPONDE SIEMPRE con un objeto JSON valido con estos campos:\n"
    '- action: "respond" | "ask_question" | "tool_call"\n'
    '- response: texto final para el usuario (solo si action="respond")\n'
    '- question: pregunta para el usuario (solo si action="ask_question")\n'
    '- question_field: "date" | "time" | "name" | "generic" | null\n'
    '- tool_calls: lista de herramientas a llamar (solo si action="tool_call")\n'
    "  Cada tool call debe tener: {\"name\": \"search_properties\", \"arguments\": \"{...json...}\"}\n"
    "  USA LOS NOMBRES EXACTOS: search_properties, get_property_details, get_property_images,\n"
    "  schedule_visit, get_my_appointments, get_faq_answer, etc. NUNCA agregues prefijos como\n"
    "  'functions.' o 'function.' — solo el nombre pelado de la herramienta.\n"
    "- confidence: tu nivel de confianza de 0.0 a 1.0\n"
    "- reasoning: breve explicacion interna (no se muestra al usuario)\n\n"
    "NUNCA respondas con texto libre. Siempre usa el formato JSON. "
    'Si tenes que usar una herramienta, usa action="tool_call" y pone la herramienta en tool_calls. '
    'Si podes responder directamente, usa action="respond". '
    'Si necesitas preguntar algo, usa action="ask_question".\n'
)

_STATE_PROMPTS = {
    "qualifying": _sp(
        "El usuario recien empieza. Todavia no tengo sus criterios de busqueda. "
        "Mi trabajo es entender que busca: alquiler o compra? que tipo de propiedad? en que zona? presupuesto? cuantos ambientes?\n\n"
        "Herramientas disponibles: search_properties, get_faq_answer.\n"
        "Si el usuario ya dio criterios claros (tipo + operacion + zona + presupuesto o ambientes), busca con search_properties. REGLA ESTRICTA: si tengo 3 criterios o menos, PREGUNTO el que falta. No busco hasta completar los 4. NUNCA asumo que el usuario quiere ver todo. "
    ),
    "searching": _sp(
        "Estoy buscando propiedades para el usuario. Ya tengo algunos criterios. "
        "Herramientas: search_properties, get_property_details, get_property_images, refine_search.\n\n"
        "REGLAS:\n"
        "- Si el usuario da nuevos criterios -> search_properties con lo que tengo\n"
        "- Si el usuario elige una propiedad (por numero, ID, o direccion) -> get_property_details\n"
        "- Si search_properties no encuentra nada -> ofrezco alternativas (cambiar zona, presupuesto, tipo)\n"
        "- No pregunto datos que el usuario ya dio\n"
        "- Siempre incluyo property_type si el usuario menciono un tipo concreto\n\n"
    ),
        "viewing_property": _sp(
        "El usuario esta viendo una propiedad. El router ya detecto si quiere detalles o fotos.\n"
        "Herramientas: get_property_details, get_property_images.\n\n"
        "REGLAS:\n"
        "- Si el usuario pide agendar -> pregunta el dia\n"
        '- Si el usuario dice \"esa\", \"fotos\", \"agendar\" -> usa la propiedad activa\n\n'
    ),
    "viewing_detail": _sp(
        "El usuario pidio mas informacion de una propiedad.\n"
        "Herramienta principal: get_property_details.\n"
        "Tambien disponible: get_property_images (por si despues pide fotos).\n\n"
        "LLAMA get_property_details AHORA con el ID de la propiedad activa.\n"
        "NO preguntes si quiere ver la info — el usuario ya confirmo que SI.\n"
        "Despues de mostrar los detalles, preguntale si quiere ver fotos o agendar visita.\n\n"
    ),
    "viewing_photos": _sp(
        "El usuario pidio ver las fotos de una propiedad.\n"
        "Herramienta principal: get_property_images.\n"
        "Tambien disponible: get_property_details.\n\n"
        "LLAMA get_property_images AHORA con el ID de la propiedad activa.\n"
        "NO preguntes si quiere ver las fotos — el usuario ya confirmo que SI.\n"
        "Despues de mostrar las fotos, preguntale si quiere mas detalles o agendar visita.\n\n"
    ),
"scheduling_ask_date": _sp(
        "El usuario quiere agendar una visita. Tengo que preguntar el dia.\n"
        "Herramienta: schedule_visit.\n\n"
        'Pregunta: "Que dia te queda bien? Atendemos de lunes a sabado de 9 a 18hs."\n'
        'Cuando el usuario responda con un dia -> llama schedule_visit(property_id=X, date_str="lo que dijo").\n'
        "NO preguntes la hora todavia - schedule_visit se encarga.\n"
        "NO confirmes la propiedad de nuevo si ya esta seleccionada.\n\n"
    ),
    "scheduling_ask_time": _sp(
        "El usuario ya dio el dia. Tengo que preguntar la hora.\n"
        "Herramienta: schedule_visit.\n\n"
        'Pregunta: "A que hora te queda mejor el [dia]?"\n'
        "Cuando el usuario de la hora -> llama schedule_visit con todos los datos disponibles.\n\n"
    ),
    "scheduling_confirm": _sp(
        "Tengo dia y hora. Voy a confirmar la visita llamando schedule_visit.\n"
        "Herramienta: schedule_visit.\n\n"
        "LLAMA schedule_visit con property_id, date_str, time_str y client_name si lo tenes.\n"
        'Si la herramienta pide el nombre -> pregunta "Me decis tu nombre y apellido?"\n'
        'Si la visita se confirma -> "Cita Agendada. [Fecha] a las [Hora] en [Propiedad]. Te esperamos."\n'
        "Si se rechaza (domingo, fuera de horario) -> ofrece alternativas.\n\n"
    ),
    "scheduling_ask_name": _sp(
        "La herramienta schedule_visit pidio el nombre del cliente.\n"
        "Herramienta: schedule_visit.\n\n"
        'Pregunta: "Me decis tu nombre y apellido?"\n'
        'Cuando el usuario de su nombre -> llama schedule_visit con client_name="el nombre".\n\n'
    ),
    "appointment_management": _sp(
        "El usuario quiere gestionar sus citas: reprogramar o cancelar.\n"
        "Herramientas: get_my_appointments, reschedule_appointment, cancel_appointment.\n\n"
        "PASO 1: Llama get_my_appointments para mostrar las citas.\n"
        "PASO 2: Cuando el usuario elija una (por numero), busca el UUID en <!--ID:N:uuid-->.\n"
        "PASO 3: Llama reschedule_appointment o cancel_appointment con ese UUID.\n\n"
    ),
    "faq": _sp(
        "El usuario tiene una consulta sobre la inmobiliaria.\n"
        "Herramienta: get_faq_answer.\n\n"
        "Llama get_faq_answer con la pregunta del usuario. "
        "Usa la respuesta de la herramienta. Si no hay informacion, deci que no tengo ese dato "
        "y ofrece ayuda con propiedades o visitas.\n"
        'Despues de responder: "Te queda alguna duda o quisieras consultar algo mas?"\n\n'
    ),
    "out_of_scope": _sp(
        "Esto esta fuera de mi alcance. Solo puedo ayudar con propiedades, alquileres y visitas.\n"
        "Responde redirigiendo al negocio inmobiliario.\n\n"
    ),
    "human_assistance": _sp(
        "El usuario necesita hablar con un agente humano.\n"
        "Herramienta: request_human_assistance.\n\n"
        "Llama request_human_assistance. Responde que un agente lo contactara pronto.\n\n"
    ),
    "default": _sp(
        "Puedo buscar propiedades, mostrar fotos, responder consultas y agendar visitas.\n"
        "Herramientas: search_properties, get_property_details, get_property_images, get_faq_answer.\n\n"
    ),
}


def get_state_prompt(state: str, user_context: Dict[str, Any] = None) -> str:
    """v2.0: Returns a focused prompt for the current state.

    Args:
        state: Current state machine state
        user_context: Optional user preferences dict

    Returns:
        State-specific system prompt string
    """
    from datetime import datetime
    import pytz

    if user_context is None:
        user_context = {}

    db_settings = _get_cached_bot_settings()
    if db_settings.get("company_name"):
        company_name = db_settings["company_name"]
    else:
        try:
            from app.core.config import get_settings
            company_name = get_settings().COMPANY_NAME or "la inmobiliaria"
        except Exception:
            company_name = "la inmobiliaria"

    prompt = _STATE_PROMPTS.get(state, _STATE_PROMPTS["default"])
    prompt = prompt.replace("{company_name}", company_name)

    context_lines = []
    user_name = user_context.get("name") or user_context.get("user_name") or ""
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
