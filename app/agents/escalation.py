"""Confidence-based escalation system (Phase 3).

Implements the stratified autonomy thresholds from the roadmap:
  ≥ 0.95  → EXECUTE (autonomous)
  0.70+   → VERIFY (confirm with user)
  0.50+   → CLARIFY (ask for more detail)
  < 0.50  → HANDOFF (fallback)
"""

from enum import Enum


class EscalationLevel(str, Enum):
    EXECUTE = "execute"
    VERIFY = "verify"
    CLARIFY = "clarify"
    HANDOFF = "handoff"


# Confidence thresholds
THRESHOLD_EXECUTE = 0.95
THRESHOLD_VERIFY = 0.70
THRESHOLD_CLARIFY = 0.50


def assess_confidence(raw_confidence: float) -> tuple[EscalationLevel, float]:
    """Clamp and classify confidence into an escalation level.

    Returns (level, clamped_confidence).
    """
    clamped = max(0.0, min(1.0, raw_confidence))

    if clamped >= THRESHOLD_EXECUTE:
        return EscalationLevel.EXECUTE, clamped
    elif clamped >= THRESHOLD_VERIFY:
        return EscalationLevel.VERIFY, clamped
    elif clamped >= THRESHOLD_CLARIFY:
        return EscalationLevel.CLARIFY, clamped
    else:
        return EscalationLevel.HANDOFF, clamped


def build_clarification_message(level: EscalationLevel, original_response: str) -> str:
    """Modify or replace the response based on the escalation level.

    - EXECUTE: pass through unchanged
    - VERIFY: append confirmation prompt
    - CLARIFY: replace with a focused clarifying question
    - HANDOFF: replace with a graceful fallback
    """
    if level == EscalationLevel.EXECUTE:
        return original_response

    if level == EscalationLevel.VERIFY:
        # Append a gentle verification prompt if not already present
        if "¿" in original_response and original_response.strip().endswith("?"):
            return original_response
        return f"{original_response}\n\n¿Entendí bien? Confirmame y sigo."

    if level == EscalationLevel.CLARIFY:
        # Don't replace the LLM's response — append a gentle nudge
        if len(original_response) < 15:
            return (
                "No me quedó del todo claro. ¿Podrías darme más detalles?\n\n"
                "Por ejemplo: ¿buscás alquilar o comprar? ¿En qué zona? "
                "¿Cuál es tu presupuesto aproximado?"
            )
        return original_response

    # HANDOFF
    return (
        "Disculpá, no estoy seguro de entenderte bien. 😕\n\n"
        "¿Podrías explicarlo de otra forma? También podés consultarme sobre:\n"
        "• Buscar propiedades (alquiler o venta)\n"
        "• Requisitos para alquilar\n"
        "• Zonas y precios en Oberá\n"
        "• Agendar una visita"
    )
