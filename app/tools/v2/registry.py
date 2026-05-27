"""Tool registry — maps tool names to callables and provides OpenAI tool schemas."""

from typing import Any, Callable

from app.agents.schemas import StructuredToolCall
from app.tools.v2.v2.echo_tool import echo
from app.tools.v2.v2.time_tool import get_time
from app.tools.v2.v2.search_properties import search_properties
from app.tools.v2.v2.get_property_details import get_property_details
from app.tools.v2.v2.get_property_images import get_property_images
from app.tools.v2.v2.get_faq_answer import get_faq_answer
from app.tools.v2.v2.schedule_visit import schedule_visit

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
                    "Busca propiedades en Oberá según los criterios del usuario. "
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
                            "description": "Zona o barrio en Oberá: 'Centro', 'UNAM', 'Barrio Schuster', 'Ruta 14'.",
                        },
                        "presupuesto_max": {
                            "type": "number",
                            "description": "Presupuesto máximo en pesos argentinos. 0 = sin límite.",
                        },
                        "dormitorios": {
                            "type": "integer",
                            "description": "Cantidad mínima de dormitorios. 0 = sin filtro.",
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
                    "Si faltan datos (nombre, teléfono), la herramienta los va a pedir."
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
                            "description": "Número de teléfono o WhatsApp del interesado.",
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
}


def get_tools_schema() -> list[dict[str, Any]]:
    """Return the OpenAI tool schemas for all registered tools."""
    return [schema for _, _, schema in TOOL_REGISTRY.values()]


async def execute_tool(tool_call: StructuredToolCall) -> str:
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
