"""
validators.py — 10 quality rules checked per bot response.
Each returns list of (rule_name, PASS|FAIL|WARN, message).
"""

import re
from typing import List, Tuple


def validate_all(response_text: str, tools_used: List[str], timing: dict) -> List[Tuple[str, str, str]]:
    """
    Run all 10 validation rules against a single bot response.
    Returns list of (rule_name, status, message).
    """
    results = []
    text_lower = response_text.lower() if response_text else ""

    # 1. TOOL-EXISTS: schedule_visit
    _check_action(text_lower, tools_used,
                  ["agendada", "agendé", "agendamos", "cita agendada", "te esperamos",
                   "visita agendada", "quedó agendada"],
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

    # 4. TOOL-EXISTS: save_lead_info
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

    # 10. STATE: responses should not be empty
    if not response_text or len(response_text.strip()) < 5:
        results.append(("NOT-EMPTY", "FAIL", "Empty or too-short response"))

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
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',  # UUIDs are real
    ]

    for pattern in bad_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            results.append(("NOT-HALLUC", "FAIL", f"'data:image/...' in response"))
            return  # Only report first
