"""Parse LLM responses into structured output (Phase 3).

Handles gpt-5.4-mini's json_schema responses with fallback for
non-JSON output (legacy models or malformed responses).
"""

import json
import re


# JSON schema the LLM is instructed to follow
FINAL_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "final_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "respuesta": {
                    "type": "string",
                    "description": "La respuesta final para el usuario, en español.",
                },
                "confianza": {
                    "type": "number",
                    "description": (
                        "Nivel de confianza del 0 al 1. "
                        "≥0.95: certeza total (saludos, hechos). "
                        "0.70-0.95: bastante seguro pero requiere confirmación. "
                        "0.50-0.70: entendimiento parcial, falta información. "
                        "<0.50: no se entendió bien, mejor derivar."
                    ),
                },
            },
            "required": ["respuesta", "confianza"],
            "additionalProperties": False,
        },
    },
}


def parse_llm_response(raw_text: str) -> tuple[str, float]:
    """Parse the LLM's response into (text, confidence).

    Tries multiple strategies:
    1. Clean JSON parse (json_schema output)
    2. JSON embedded in markdown code blocks
    3. Regex extraction of JSON object
    4. Fallback: treat entire text as response, confidence=0.5
    """
    if not raw_text or not raw_text.strip():
        return "", 0.0

    text = raw_text.strip()

    # Strategy 1: Direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "respuesta" in data:
            return _safe_extract(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: JSON in markdown code block
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_match:
        try:
            data = json.loads(code_match.group(1).strip())
            if isinstance(data, dict) and "respuesta" in data:
                return _safe_extract(data)
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: Find JSON object with respuesta field
    json_match = re.search(r'\{"respuesta"\s*:\s*".*?"\s*,\s*"confianza"\s*:\s*[\d.]+}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict) and "respuesta" in data:
                return _safe_extract(data)
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Try to find any JSON object
    json_match = re.search(r"\{[^{}]*\}", text)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict):
                resp = data.get("respuesta") or data.get("response") or data.get("text", "")
                conf = data.get("confianza") or data.get("confidence") or data.get("conf", 0.5)
                return str(resp), float(conf)
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: treat entire text as response
    return text, 0.5


def _safe_extract(data: dict) -> tuple[str, float]:
    """Extract respuesta and confianza with type coercion."""
    respuesta = str(data.get("respuesta", ""))
    try:
        confianza = float(data.get("confianza", 0.5))
    except (TypeError, ValueError):
        confianza = 0.5
    return respuesta, max(0.0, min(1.0, confianza))
