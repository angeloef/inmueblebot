"""Tool registry — maps tool names to callables and provides OpenAI tool schemas."""

from typing import Any, Callable

from app.agents.schemas import CSStructuredToolCall
from app.tools.v2.echo_tool import echo
from app.tools.v2.time_tool import get_time
from app.tools.v2.search_properties import search_properties
from app.tools.v2.get_property_details import get_property_details
from app.tools.v2.get_property_images import get_property_images
from app.tools.v2.get_faq_answer import get_faq_answer
from app.tools.v2.schedule_visit import schedule_visit
from app.tools.v2.get_my_appointments import get_my_appointments
from app.tools.v2.cancel_appointment import cancel_appointment
from app.tools.v2.reschedule_appointment import reschedule_appointment
from app.tools.v2.request_human_assistance import request_human_assistance

# Registry: tool name → (function, is_async, schema dict)
TOOL_REGISTRY: dict[str, tuple[Callable[..., Any], bool, dict[str, Any]]] = {
    "echo": (
        echo,
        False,
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Repite un mensaje de vuelta. Usar cuando el usuario pide repetir algo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "El texto a repetir",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
    ),
    "get_time": (
        get_time,
        False,
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Devuelve la fecha y hora actual en Argentina (ART, UTC-3).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ),
    "search_properties": (
        search_properties,
        True,
        {
            "type": "function",
            "function": {
                "name": "search_properties",
                "description": (
                    "Busca propiedades de la inmobiliaria según los criterios del usuario. "
                    "Siempre usar esta herramienta cuando el usuario quiera buscar, alquilar o comprar. "
                    "Todos los filtros son opcionales; los omitidos matchean cualquier valor."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["alquiler", "venta", ""],
                            "description": "Tipo de operación: 'alquiler' (renta) o 'venta' (compra). Dejar vacío si no está claro.",
                        },
                        "tipo": {
                            "type": "string",
                            "description": (
                                "Tipo de propiedad: 'departamento' (o 'depto'), 'casa', 'ph', 'terreno'. "
                                "Mapear 'departamentos'/'deptos' a 'departamento', 'casas' a 'casa'."
                            ),
                        },
                        "zona": {
                            "type": "string",
                            "description": (
                                "Zona, barrio, ciudad, o punto de referencia cercano donde busca el usuario "
                                "(ej: 'Centro', 'Belgrano', 'Oberá', 'hospital', 'terminal', 'plaza'). "
                                "Las variantes de escritura de ciudades se resuelven automáticamente. "
                                "Incluir el término exacto que usó el usuario."
                            ),
                        },
                        "presupuesto_max": {
                            "type": "number",
                            "description": "Presupuesto máximo en pesos argentinos. 0 = sin límite.",
                        },
                        "ambientes": {
                            "type": "integer",
                            "description": "Total de ambientes (AR: espacios habitables). 1 = monoambiente. 0 = sin filtro. Usar cuando el usuario dice '2 ambientes', 'monoambiente', 'ambiente y medio', etc. Preferir sobre dormitorios cuando el usuario usa el término 'ambiente'.",
                        },
                        "ambientes_match": {
                            "type": "string",
                            "enum": ["exact", "at_least", "range"],
                            "description": "Modo de match para ambientes: 'exact', 'at_least', 'range'. Default: 'exact'.",
                        },
                        "ambientes_max": {
                            "type": "integer",
                            "description": "Máximo de ambientes, solo cuando ambientes_match='range'. 0 = sin límite.",
                        },
                        "dormitorios": {
                            "type": "integer",
                            "description": "Cantidad de dormitorios (sin contar sala/living). 0 = sin filtro. Usar cuando el usuario dice '1 dormitorio', '2 habitaciones', etc. Para 'monoambiente' usar ambientes=1.",
                        },
                        "bedrooms_match": {
                            "type": "string",
                            "enum": ["exact", "at_least", "range"],
                            "description": "Como matchear dormitorios: 'exact', 'at_least', 'range'. Default: 'exact'.",
                        },
                        "dormitorios_max": {
                            "type": "integer",
                            "description": "Máximo de dormitorios, solo cuando bedrooms_match='range'. 0 = sin límite.",
                        },
                    },
                },
            },
        },
    ),
    "get_property_details": (
        get_property_details,
        True,
        {
            "type": "function",
            "function": {
                "name": "get_property_details",
                "description": (
                    "Muestra todos los detalles de una propiedad específica por su ID. "
                    "Usar cuando el usuario pide más información sobre un resultado de búsqueda, "
                    "por ejemplo 'mostrame más del 3' o 'quiero ver el departamento 5'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "property_id": {
                            "type": "integer",
                            "description": "El ID numérico de la propiedad (el número entre corchetes en los resultados de búsqueda).",
                        },
                    },
                    "required": ["property_id"],
                },
            },
        },
    ),
    "get_property_images": (
        get_property_images,
        True,
        {
            "type": "function",
            "function": {
                "name": "get_property_images",
                "description": (
                    "Muestra las fotos disponibles de una propiedad. "
                    "Usar cuando el usuario pide ver fotos o imágenes de un resultado específico."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "property_id": {
                            "type": "integer",
                            "description": "El ID numérico de la propiedad.",
                        },
                    },
                    "required": ["property_id"],
                },
            },
        },
    ),
    "get_faq_answer": (
        get_faq_answer,
        True,
        {
            "type": "function",
            "function": {
                "name": "get_faq_answer",
                "description": (
                    "Responde preguntas frecuentes sobre alquiler, compra, requisitos, garantías, etc. "
                    "Usar cuando el usuario hace preguntas sobre el proceso de alquilar/comprar."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pregunta": {
                            "type": "string",
                            "description": (
                                "La pregunta o tema sobre el que el usuario quiere información. "
                                "Ejemplos: 'requisitos', 'garantía', 'contrato', 'mascotas', 'visita', 'zonas', 'precios', 'contacto'."
                            ),
                        },
                    },
                    "required": ["pregunta"],
                },
            },
        },
    ),
    "schedule_visit": (
        schedule_visit,
        True,
        {
            "type": "function",
            "function": {
                "name": "schedule_visit",
                "description": (
                    "Agenda una visita para ver una propiedad. Usar cuando el usuario quiere coordinar "
                    "una visita, ver un departamento, o preguntar cuándo puede ir a conocer una propiedad. "
                    "Si falta el nombre o el día, la herramienta los va a pedir. NO pidas el teléfono: "
                    "la identidad/contacto sale del WhatsApp del usuario."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "property_id": {
                            "type": "integer",
                            "description": "El ID de la propiedad que el usuario quiere visitar.",
                        },
                        "nombre": {
                            "type": "string",
                            "description": "Nombre completo del interesado.",
                        },
                        "telefono": {
                            "type": "string",
                            "description": "OPCIONAL. Número de contacto alternativo, solo si el usuario lo ofrece. NO lo pidas — el teléfono/identidad ya viene del WhatsApp del usuario.",
                        },
                        "dia": {
                            "type": "string",
                            "description": "Día preferido para la visita (ej: 'viernes', 'martes 15').",
                        },
                        "horario": {
                            "type": "string",
                            "description": "Horario preferido (ej: '15:00', 'por la tarde', 'a las 11').",
                        },
                        "consulta": {
                            "type": "string",
                            "description": "Cualquier consulta adicional del interesado.",
                        },
                    },
                },
            },
        },
    ),
    "get_my_appointments": (
        get_my_appointments,
        True,
        {
            "type": "function",
            "function": {
                "name": "get_my_appointments",
                "description": "Lista las visitas YA agendadas del usuario. Usar cuando pregunta 'qué citas/visitas tengo', 'cuándo me agendé', etc.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ),
    "cancel_appointment": (
        cancel_appointment,
        True,
        {
            "type": "function",
            "function": {
                "name": "cancel_appointment",
                "description": "Cancela una visita agendada del usuario. Si tiene varias, pasá 'cual' con una pista (día o id de propiedad); si no, la herramienta pregunta cuál.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cual": {"type": "string", "description": "Pista para elegir cuál cancelar si hay varias: día (ej 'jueves'), dd/mm, o id de propiedad."},
                        "motivo": {"type": "string", "description": "Razón opcional de la cancelación."},
                    },
                },
            },
        },
    ),
    "reschedule_appointment": (
        reschedule_appointment,
        True,
        {
            "type": "function",
            "function": {
                "name": "reschedule_appointment",
                "description": "Reprograma (cambia día/hora) una visita ya agendada del usuario. Usar para 'cambiá mi visita al jueves', 'movela a las 4', etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dia": {"type": "string", "description": "Nuevo día (ej 'jueves', 'martes 02/06', 'mañana')."},
                        "horario": {"type": "string", "description": "Nuevo horario (ej '15:00', 'a las 3 de la tarde')."},
                        "cual": {"type": "string", "description": "Pista para elegir cuál reprogramar si hay varias."},
                    },
                },
            },
        },
    ),
    "request_human_assistance": (
        request_human_assistance,
        True,
        {
            "type": "function",
            "function": {
                "name": "request_human_assistance",
                "description": (
                    "Transfiere la conversación a un agente humano. Usar cuando el usuario pide hablar con una persona, "
                    "el bot no puede resolver el problema, o la situación requiere atención personalizada. "
                    "El bot se pausa automáticamente después de llamar esta herramienta."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string", "description": "Por qué se necesita un agente humano."},
                        "message": {"type": "string", "description": "Mensaje personalizado opcional para el usuario."},
                    },
                },
            },
        },
    ),
}


def get_tools_schema() -> list[dict[str, Any]]:
    """Return the OpenAI tool schemas for all registered tools."""
    return [schema for _, _, schema in TOOL_REGISTRY.values()]


# Alias used by s2_agent and other callers that import get_tools_openai_schema
get_tools_openai_schema = get_tools_schema


def validate_tool_args(name: str, args: dict) -> tuple[bool, str]:
    """Returns (is_valid, error_message). Checks required args are present."""
    tool_entry = TOOL_REGISTRY.get(name)
    if not tool_entry:
        return False, f"Tool '{name}' not found in registry"

    # Get the schema from the tool's OpenAI definition (third element of tuple)
    _, _, tool_schema = tool_entry
    required = tool_schema.get("function", {}).get("parameters", {}).get("required", [])
    missing = [r for r in required if r not in args or args[r] is None]

    if missing:
        return False, f"Missing required args for {name}: {missing}"
    return True, ""


async def execute_tool(tool_call: CSStructuredToolCall) -> str:
    """Execute a tool by name and return its string result.

    Handles both sync and async tools transparently.
    """
    if tool_call.name not in TOOL_REGISTRY:
        available = ", ".join(TOOL_REGISTRY.keys())
        return f"Error: herramienta '{tool_call.name}' no encontrada. Disponibles: {available}"

    func, is_async, _ = TOOL_REGISTRY[tool_call.name]

    try:
        if is_async:
            result = await func(**tool_call.arguments)
        else:
            result = func(**tool_call.arguments)
        return str(result) if result is not None else "ok"
    except TypeError as e:
        return f"Error: argumentos inválidos para '{tool_call.name}': {e}"
    except Exception as e:
        return f"Error ejecutando '{tool_call.name}': {e}"
