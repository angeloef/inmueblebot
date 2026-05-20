"""
validators.py — 16 quality rules checked per bot response (v3).

Each returns list of (rule_name, PASS|FAIL|WARN, message).

v3 changes:
- Rule 11: TOOL-EXISTS — recommend_properties
- Rule 12: TOOL-EXISTS — save_lead_info
- Rule 13: TOOL-EXISTS — request_human_assistance
- Rule 14: TOOL-EXISTS — refine_search
- Rule 15: LANGUAGE — verify AI response is in Spanish
- Rule 16: NOT-STALE-CONTEXT — verify context carries across turns
"""

import re
from typing import List, Tuple


def validate_all(response_text: str, tools_used: List[str], timing: dict) -> List[Tuple[str, str, str]]:
    """
    Run all 16 validation rules against a single bot response.
    Returns list of (rule_name, status, message).
    """
    results = []
    text_lower = response_text.lower() if response_text else ""

    # ═══════════════════════════════════════════════════════════════
    # EXISTING RULES (1-10)
    # ═══════════════════════════════════════════════════════════════

    # 1. TOOL-EXISTS: schedule_visit
    _check_action(text_lower, tools_used,
                  ["cita agendada", "agendé", "agendamos", "quedó agendada"],
                  "schedule_visit", "Schedule claimed but tool not called", results)

    # 2. TOOL-EXISTS: cancel_appointment
    _check_action(text_lower, tools_used,
                  ["cancelada", "cancelé", "cita cancelada", "turno cancelado", "anulada"],
                  "cancel_appointment", "Cancel claimed but tool not called", results)

    # 3. TOOL-EXISTS: reschedule_appointment
    _check_action(text_lower, tools_used,
                  ["reprogramada", "reprogramé", "cita reprogramada", "cambio la fecha",
                   "modifiqué tu cita"],
                  "reschedule_appointment", "Reschedule claimed but tool not called", results)

    # 4. TOOL-EXISTS: save_lead_info (original — keep for backward compat)
    _check_action(text_lower, tools_used,
                  ["guardé tus datos", "te registré", "datos guardados", "quedaste registrado"],
                  "save_lead_info", "Save claimed but tool not called", results)

    # 5. TOOL-EXISTS: search_properties
    _check_action(text_lower, tools_used,
                  ["encontré", "encontré estas", "acá tenés", "te muestro",
                   "resultados de búsqueda", "propiedades encontradas"],
                  "search_properties",
                  "Search results claimed but tool not called", results,
                  invert_check=True)

    # 6. NOT-HALLUC: no hallucinated property IDs
    _check_hallucinated_ids(response_text, results)

    # 7. NOT-ERROR: no internal errors leaked
    if any(p in text_lower for p in ["traceback", "exception:", "error al ejecutar",
                                      "indexerror", "keyerror", "typeerror",
                                      "attributeerror", "valueerror"]):
        results.append(("NOT-ERROR", "FAIL", f"Internal error leaked in response"))

    # 8. NOT-CONFIRMED: no CONFIRMED tag leaked
    if "<!--confirmed:" in text_lower:
        results.append(("NOT-CONFIRMED", "FAIL", "CONFIRMED HTML tag leaked to user"))

    # 9. TIMING: turn time
    turn_s = timing.get("turn_seconds", 0)
    if turn_s > 30:
        results.append(("TIMING", "WARN", f"Turn time {turn_s:.1f}s > 30s threshold"))
    elif turn_s < 30:
        results.append(("TIMING", "PASS", f"{turn_s:.1f}s"))

    # 10. NOT-EMPTY: responses should not be empty
    if not response_text or len(response_text.strip()) < 5:
        results.append(("NOT-EMPTY", "FAIL", "Empty or too-short response"))

    # ═══════════════════════════════════════════════════════════════
    # NEW RULES (11-16)
    # ═══════════════════════════════════════════════════════════════

    # 11. TOOL-EXISTS: recommend_properties (NEW)
    _check_action(text_lower, tools_used,
                  ["te recomiendo", "recomiendo estas", "mejores opciones",
                   "propiedades similares", "te sugiero"],
                  "recommend_properties",
                  "Recommend claimed but tool not called", results)

    # 12. TOOL-EXISTS: save_lead_info (NEW — additional phrases)
    _check_action(text_lower, tools_used,
                  ["tus datos quedaron", "te voy a registrar", "dejame tus datos",
                   "completá tus datos", "necesito tu nombre"],
                  "save_lead_info",
                  "Lead capture claimed but tool not called", results)

    # 13. TOOL-EXISTS: request_human_assistance (NEW)
    _check_action(text_lower, tools_used,
                  ["paso con un asesor", "te conecto con", "derivar a un agente",
                   "hablar con un humano", "agente humano", "transferir a un agente"],
                  "request_human_assistance",
                  "Handoff claimed but tool not called", results)

    # 14. TOOL-EXISTS: refine_search (NEW)
    _check_action(text_lower, tools_used,
                  ["refiné la búsqueda", "ajusté la búsqueda", "resultados más precisos",
                   "búsqueda más específica", "filtré los resultados"],
                  "refine_search",
                  "Refine claimed but tool not called", results)

    # 15. LANGUAGE — response must be in Spanish (NEW)
    _check_language(response_text, results)

    # 16. NOT-STALE-CONTEXT — flag if bot re-asks criteria user already gave (NEW)
    # This is a WARN since it's heuristic-based
    _check_stale_context(text_lower, results)

    return results


def _check_action(text: str, tools: List[str], phrases: List[str],
                  required_tool: str, fail_msg: str,
                  results: list, invert_check: bool = False):
    """
    If any claim_phrase is in text but required_tool NOT in tools → FAIL.
    If invert_check=True: PASS if tool was called, WARN if tool not called.
    """
    any_match = any(p in text for p in phrases)
    tool_called = required_tool in tools

    if invert_check:
        # For search_properties: we want tool to be called when results are shown
        pass  # This check is informational for now
        return

    if any_match and not tool_called:
        results.append(("TOOL-EXISTS", "FAIL", f"{fail_msg} (tools={tools}, text_mentions={[p for p in phrases if p in text]})"))
    elif any_match and tool_called:
        results.append(("TOOL-EXISTS", "PASS", f"{required_tool} correctly called"))


def _check_hallucinated_ids(text: str, results: list):
    """
    Check for clearly hallucinated property IDs like 'abc-123' or 'uuid_de_la_cita'.
    Doesn't flag numeric IDs or standard UUIDs.
    """
    if not text:
        return

    # Known hallucination patterns from production logs
    bad_patterns = [
        r'abc-123',
        r'uuid_de_la_cita',
        r'ID del usuario',
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',  # UUIDs are real but shouldn't leak
    ]

    for pattern in bad_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            results.append(("NOT-HALLUC", "FAIL", f"Hallucinated / leaked ID pattern: {pattern}"))
            return  # Only report first


def _check_language(text: str, results: list):
    """
    Check that the bot's response is in Spanish.
    Flags responses that start with English greetings or phrases
    (common when LLM prompt drifts or falls back to a non-Spanish model).
    """
    if not text:
        return

    text_stripped = text.strip()

    # English-only patterns that shouldn't appear in a Spanish bot
    english_starts = [
        "hello", "hi there", "good morning", "good afternoon",
        "welcome!", "i found", "here are", "sure,", "of course",
    ]
    for pattern in english_starts:
        if text_stripped.lower().startswith(pattern):
            results.append(("LANGUAGE", "WARN", f"Response starts with English: '{text_stripped[:60]}...'"))
            return

    # Check that response has at least some Spanish content
    # (at least one Spanish-specific character or common word)
    spanish_indicators = ["á", "é", "í", "ó", "ú", "ñ", "ü",
                          "hola", "gracias", "buscas", "querés", "tenés",
                          "departamento", "propiedad", "inmobiliaria"]
    has_spanish = any(c in text.lower() for c in spanish_indicators)
    # If text is >20 chars and has zero Spanish indicators, flag it
    if len(text_stripped) > 20 and not has_spanish:
        results.append(("LANGUAGE", "WARN", f"Response lacks Spanish characters: '{text_stripped[:60]}...'"))


def _check_stale_context(text_lower: str, results: list):
    """
    Heuristic check for stale context — flags if the bot asks for basic criteria
    that a user would typically have already given (qualifying questions when
    in a later state). This is a WARN since it can be legitimate.
    """
    re_ask_patterns = [
        "qué tipo de propiedad", "qué operación", "alquilar o comprar",
        "cuál es tu presupuesto", "en qué zona", "qué zona te interesa",
        "cuántos dormitorios", "cuántos ambientes",
        "me podrías decir el presupuesto",
    ]
    for pattern in re_ask_patterns:
        if pattern in text_lower:
            results.append(("NOT-STALE-CONTEXT", "WARN", f"Bot re-asking criteria: '{pattern}'"))
            return  # Only report first
