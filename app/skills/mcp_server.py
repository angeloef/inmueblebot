"""MCP (Model Context Protocol) JSON-RPC 2.0 server.

Exposes all registered skills as MCP tools via a standard endpoint.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from app.skills.registry import get_skill_registry


MCP_VERSION = "2024-11-05"


@dataclass
class MCPResponse:
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: Optional[int] = None
    result: Optional[Any] = None
    error: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.error:
            d["error"] = self.error
        elif self.result is not None:
            d["result"] = self.result
        return d


def handle_mcp_request(body: dict) -> dict:
    """Handle a JSON-RPC 2.0 MCP request.

    Supported methods:
    - initialize: MCP handshake
    - tools/list: list all available tools
    - tools/call: execute a tool
    """
    method = body.get("method", "")
    request_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return _respond(request_id, {
            "protocolVersion": MCP_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "ChatbotSerio",
                "version": "0.1.0",
            },
        })

    if method == "tools/list":
        registry = get_skill_registry()
        tools = registry.get_mcp_tools()
        return _respond(request_id, {"tools": tools})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Route to the appropriate handler
        result = _execute_skill_tool(tool_name, arguments)
        return _respond(request_id, {
            "content": [{"type": "text", "text": result}]
        })

    return _error(request_id, -32601, f"Method not found: {method}")


def handle_mcp_request_raw(raw_body: str) -> str:
    """Handle a raw MCP JSON-RPC request string."""
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return json.dumps(_error(None, -32700, "Parse error").to_dict())

    response = handle_mcp_request(body)
    return json.dumps(response.to_dict())


def _respond(request_id, result):
    return MCPResponse(id=request_id, result=result)


def _error(request_id, code: int, message: str):
    return MCPResponse(id=request_id, error={"code": code, "message": message})


def _execute_skill_tool(tool_name: str, arguments: dict) -> str:
    """Execute a skill by name in a fresh event loop."""
    import asyncio
    import concurrent.futures

    handlers = {
        "search_properties": _run_search,
        "get_property_details": _run_details,
        "get_property_images": _run_images,
        "get_faq_answer": _run_faq,
        "schedule_visit": _run_schedule,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return f"Error: unknown tool '{tool_name}'"

    try:
        # Always run in a separate thread with a fresh event loop
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(handler, arguments)
            return future.result(timeout=10)
    except Exception as e:
        return f"Error executing '{tool_name}': {e}"


def _run_search(args: dict) -> str:
    import asyncio
    from app.tools.v2.search_properties import search_properties
    return asyncio.run(search_properties(
        operation=args.get("operation", ""),
        tipo=args.get("tipo", args.get("property_type", "")),
        zona=args.get("zona", args.get("zone", "")),
        presupuesto_max=float(args.get("presupuesto_max", 0)),
        dormitorios=int(args.get("dormitorios", 0)),
    ))


def _run_details(args: dict) -> str:
    import asyncio
    from app.tools.v2.get_property_details import get_property_details
    return asyncio.run(get_property_details(property_id=int(args.get("property_id", 0))))


def _run_images(args: dict) -> str:
    import asyncio
    from app.tools.v2.get_property_images import get_property_images
    return asyncio.run(get_property_images(property_id=int(args.get("property_id", 0))))


def _run_faq(args: dict) -> str:
    import asyncio
    from app.tools.v2.get_faq_answer import get_faq_answer
    return asyncio.run(get_faq_answer(pregunta=args.get("pregunta", args.get("message", ""))))


def _run_schedule(args: dict) -> str:
    prop_id = args.get("property_id", "?")
    nombre = args.get("nombre", args.get("name", "No especificado"))
    telefono = args.get("telefono", args.get("phone", "No especificado"))
    dia = args.get("dia", args.get("day", "a coordinar"))
    horario = args.get("horario", args.get("time", "a coordinar"))

    return (
        f"✅ Visita agendada (simulación)\n"
        f"Propiedad: ID {prop_id}\n"
        f"Interesado: {nombre}\n"
        f"Contacto: {telefono}\n"
        f"Día: {dia} | Horario: {horario}\n"
        f"Te confirmamos la visita por WhatsApp."
    )


