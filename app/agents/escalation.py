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


def build_clarification_message(level: EscalationLevel, original_response: str, belief=None) -> str:
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
            anchored = _reanchor(belief)
            if anchored:
                return anchored
            return (
                "Contame un poco más así te ayudo mejor. "
                "¿Buscás alquilar o comprar, y en qué zona de Oberá?"
            )
        return original_response

    # HANDOFF
    anchored = _reanchor(belief)
    if anchored:
        return anchored
    return (
        "Quiero ayudarte bien. ¿Te interesa que busquemos una propiedad "
        "para alquilar o comprar en Oberá, o preferís coordinar una visita?"
    )


_AWAITING_REANCHOR = {
    "scheduling_property": "Disculpá, ¿qué propiedad te gustaría visitar? Decime el número o el tipo.",
    "scheduling_name": "Disculpá, ¿me decís el nombre completo de la persona que va a la visita?",
    "scheduling_day": "Disculpá, ¿qué día te queda bien para la visita?",
    "scheduling_time": "Disculpá, ¿a qué horario preferís la visita?",
    "scheduling_confirm": "¿Confirmamos la visita? Respondé Sí para agendarla o No para cambiar algo.",
}


def _reanchor(belief) -> "str | None":
    """Re-ask the pending question instead of dead-ending. Returns None if nothing pending."""
    awaiting = getattr(belief, "awaiting", None) if belief is not None else None
    if awaiting and awaiting in _AWAITING_REANCHOR:
        return _AWAITING_REANCHOR[awaiting]
    if awaiting:
        return f"Disculpá, ¿me confirmás {awaiting.replace('scheduling_', '').replace('_', ' ')}?"
    return None
