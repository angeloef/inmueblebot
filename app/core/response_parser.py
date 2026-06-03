"""Parse LLM responses into structured output (Phase 3).

Handles gpt-5.4-mini's json_schema responses with fallback for
non-JSON output (legacy models or malformed responses).
"""

import json
import re


_STRICT_RESPONSE_SCHEMA = {
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
                "correcciones": {
                    "type": ["string", "null"],
                    "description": (
                        "AUTO-CORRECCIÓN del estado. Cadena JSON con los campos del "
                        "[ESTADO ACTUAL] que están MAL o FALTAN respecto a lo que el "
                        "usuario realmente dijo (interpretando typos, slang y contexto), "
                        "o null si todo está correcto. Campos válidos: "
                        "operation('alquiler'|'venta'), property_type, zone, "
                        "budget_max(número en ARS), bedrooms_min(entero), "
                        "scheduling_day(ej 'viernes'), scheduling_time('HH:MM'), "
                        "scheduling_name. Ejemplo: "
                        "'{\"scheduling_day\": \"viernes\", \"budget_max\": 50000000}'"
                    ),
                },
                "mensajes": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": (
                        "SÓLO cuando el usuario hizo VARIAS preguntas distintas en un "
                        "mismo mensaje: una respuesta autocontenida por pregunta, en el "
                        "mismo orden, para enviarlas como mensajes separados y secuenciales. "
                        "Si hay una sola pregunta o no aplica, devolvé null y usá 'respuesta'."
                    ),
                },
            },
            "required": ["respuesta", "confianza", "correcciones", "mensajes"],
            "additionalProperties": False,
        },
    },
}

# Kept for backward compatibility — prefer get_final_response_format() for new code
FINAL_RESPONSE_SCHEMA = _STRICT_RESPONSE_SCHEMA


def get_final_response_format() -> dict:
    """Return the appropriate response_format dict for the active LLM provider.

    OpenAI supports strict json_schema; DeepSeek/OpenRouter only support json_object.
    The parse_llm_response() fallback chain handles both formats correctly.
    """
    from app.agents.cs_llm_client import supports_strict_json_schema
    if supports_strict_json_schema():
        return _STRICT_RESPONSE_SCHEMA
    return {"type": "json_object"}


def parse_llm_response(raw_text: str) -> tuple[str, float]:
    """Parse the LLM's response into (text, confidence).

    Tries multiple strategies:
    1. Clean JSON parse
    1b. Normalize unescaped newlines then parse (handles some LLMs)
    2. JSON embedded in markdown code blocks
    3. Regex extraction of JSON object
    3b. Truncated JSON — extract respuesta content even if JSON is incomplete
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

    # Strategy 1b: Fix unescaped literal newlines inside JSON strings
    # Some LLMs (DeepSeek) output JSON with raw newlines inside string values.
    try:
        fixed = _fix_json_newlines(text)
        data = json.loads(fixed)
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

    # Strategy 3b: Truncated JSON — extract whatever content is in the respuesta field
    # Handles the case where the JSON was cut off mid-string (token limit exceeded).
    if '"respuesta"' in text:
        m = re.search(r'"respuesta"\s*:\s*"([\s\S]+)', text)
        if m:
            content = m.group(1)
            # Unescape JSON string escapes
            content = content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            # Strip trailing incomplete JSON characters (cut-off JSON debris)
            content = content.rstrip('",\n\\} \t')
            if content:
                conf_m = re.search(r'"confianza"\s*:\s*([\d.]+)', text)
                conf = float(conf_m.group(1)) if conf_m else 0.7
                return content.strip(), conf

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


def parse_corrections(raw_text: str) -> dict:
    """Extract the optional 'correcciones' object the LLM emits to self-correct
    wrong/missing belief-state fields.

    The field is a JSON-encoded string (strict schema) OR a nested object
    (json_object mode). Returns a plain dict of {field: value}, or {} if absent.
    Best-effort: never raises.
    """
    if not raw_text or "correccion" not in raw_text.lower():
        return {}

    # Try a sequence of candidate JSON blobs (direct, newline-fixed, code block).
    candidates: list[str] = [raw_text.strip()]
    try:
        candidates.append(_fix_json_newlines(raw_text.strip()))
    except Exception:
        pass
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_text, re.DOTALL)
    if code_match:
        candidates.append(code_match.group(1).strip())

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        corr = data.get("correcciones")
        if not corr:
            return {}
        if isinstance(corr, str):
            try:
                corr = json.loads(corr)
            except (json.JSONDecodeError, ValueError):
                continue
        if isinstance(corr, dict):
            return corr
    return {}


def parse_messages(raw_text: str) -> list[str]:
    """Extract the optional 'mensajes' array the LLM emits to answer several
    distinct questions as separate, sequential bubbles.

    The field is a JSON array of strings (strict schema / json_object mode) or a
    JSON-encoded string. Returns a list of >= 2 cleaned strings, or [] when the
    field is absent, empty, or holds a single message (use 'respuesta' then).
    Best-effort: never raises.
    """
    if not raw_text or "mensaje" not in raw_text.lower():
        return []

    candidates: list[str] = [raw_text.strip()]
    try:
        candidates.append(_fix_json_newlines(raw_text.strip()))
    except Exception:
        pass
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_text, re.DOTALL)
    if code_match:
        candidates.append(code_match.group(1).strip())

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        msgs = data.get("mensajes")
        if not msgs:
            return []
        if isinstance(msgs, str):
            try:
                msgs = json.loads(msgs)
            except (json.JSONDecodeError, ValueError):
                return []
        if isinstance(msgs, list):
            out = [str(m).strip() for m in msgs if str(m).strip()]
            return out if len(out) >= 2 else []
    return []


def _safe_extract(data: dict) -> tuple[str, float]:
    """Extract respuesta and confianza with type coercion."""
    respuesta = str(data.get("respuesta", ""))
    try:
        confianza = float(data.get("confianza", 0.5))
    except (TypeError, ValueError):
        confianza = 0.5
    return respuesta, max(0.0, min(1.0, confianza))


def _fix_json_newlines(text: str) -> str:
    """Replace literal newlines inside JSON string values with \\n escape sequences.

    Some LLMs return JSON with raw newlines inside strings, making it invalid.
    This function walks the text character by character and escapes newlines that
    appear inside JSON string values.
    """
    result = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and in_string:
            result.append(c)
            i += 1
            if i < len(text):
                result.append(text[i])
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            i += 1
            continue
        if c == '\n' and in_string:
            result.append('\\n')
        elif c == '\r' and in_string:
            result.append('\\r')
        else:
            result.append(c)
        i += 1
    return ''.join(result)
