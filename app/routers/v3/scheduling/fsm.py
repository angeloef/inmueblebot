"""Scheduling FSM — post-engine interpreter/guard (Phase 4).

Design decisions (frozen):
- D-A: FSM runs ONCE, post tool-execution, pre response-assembly.
- D-B: booking_succeeded computed in _execute_tools from <!--CONFIRMED: marker.
- D-C: Business-hours/timezone degradation handled in utils.load_tenant_hours.

This module is DETERMINISTIC — 0 LLM calls. Never calls schedule_visit.
Never raises (body wrapped in try/except → FSMResult no-op on error).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


# ── States ────────────────────────────────────────────────────────────────────

class SchedulingState:
    """String constants for FSM states."""
    IDLE = "idle"
    PROPERTY_SELECTED = "property_selected"
    NEED_DAY = "need_day"
    NEED_TIME = "need_time"
    NEED_NAME = "need_name"
    CONFIRM = "confirm"
    BOOKED = "booked"
    HANDOFF = "handoff"


# awaiting value that corresponds to each need_* state
_AWAITING_FOR_STATE = {
    SchedulingState.NEED_DAY: "scheduling_day",
    SchedulingState.NEED_TIME: "scheduling_time",
    SchedulingState.NEED_NAME: "scheduling_name",
    SchedulingState.CONFIRM: "scheduling_confirm",
}

LOOP_MAX = 3

# ── FSMResult ─────────────────────────────────────────────────────────────────

@dataclass
class FSMResult:
    """Result returned by resolve(). Only engine.py mutates belief; FSM writes back."""
    response_plan: Optional[list]  # list of ResponsePlanItem-compatible dicts or None
    booking_succeeded: bool
    override: bool          # True → _assemble_response should use response_plan instead of engine's
    next_state: str         # derived state label (informational / metrics)
    tools_add: list[str] = field(default_factory=list)  # extra tool names for metrics (unused in P4)


# ── Cue patterns ─────────────────────────────────────────────────────────────

_EXIT_CUES = [
    r"\b(chau|gracias|bye|hasta luego|no gracias|no quiero|no me interesa)\b",
    r"\bbusco\s+otra\b",
    r"\botra\s+propiedad\b",
    r"\bvolver\b",
    r"\bcambiar\s+de\s+tema\b",
]

_REJECT_CUES = [
    r"\bese\s+d[ií]a\s+no\s+(puedo|me\s+viene)\b",
    r"\bno\s+puedo\s+el\b",
    r"\bno\s+me\s+viene\s+el\b",
    r"\bno\s+me\s+queda\s+(bien|libre)\b",
    r"\botro\s+(d[ií]a|horario|hora)\b",
    r"\bcambiar?\s+(el\s+)?(d[ií]a|horario|hora)\b",
]

_NAME_CORRECTION_CUES = [
    r"\bno\s+(es|soy)\s+\w+,?\s*(es|soy)\s+\w+\b",
    r"\bme\s+llamo\s+\w+\b",
    r"\bmi\s+nombre\s+es\s+\w+\b",
    r"\bes\s+\w+\s+(no\s+\w+)\b",
]

_EXIT_RE = re.compile("|".join(_EXIT_CUES), re.IGNORECASE)
_REJECT_RE = re.compile("|".join(_REJECT_CUES), re.IGNORECASE)
_NAME_CORRECTION_RE = re.compile("|".join(_NAME_CORRECTION_CUES), re.IGNORECASE)
_NAME_TOKEN_RE = re.compile(r"\b([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]{2,}(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]{2,})?)\b")


def _is_exit(msg: str) -> bool:
    return bool(_EXIT_RE.search(msg or ""))


def _is_slot_rejection(msg: str) -> bool:
    return bool(_REJECT_RE.search(msg or ""))


def _is_name_correction(msg: str) -> bool:
    return bool(_NAME_CORRECTION_RE.search(msg or ""))


def _extract_name_from_correction(msg: str) -> str | None:
    """Extract the corrected name from a correction utterance."""
    # "no es X es Y" / "no soy X soy Y" → take the last name token
    m = _NAME_TOKEN_RE.findall(msg or "")
    if m:
        return m[-1]
    return None


def _derive_state(belief) -> str:
    """Derive the current FSM state from belief fields (no booking yet)."""
    if not getattr(belief, "selected_property_id", None):
        return SchedulingState.IDLE
    awaiting = getattr(belief, "awaiting", None)
    if awaiting == "scheduling_day":
        return SchedulingState.NEED_DAY
    if awaiting == "scheduling_time":
        return SchedulingState.NEED_TIME
    if awaiting == "scheduling_name":
        return SchedulingState.NEED_NAME
    if awaiting == "scheduling_confirm":
        return SchedulingState.CONFIRM
    # Check if scheduling fields suggest we're mid-flow
    day = getattr(belief, "scheduling_day", "") or ""
    time_ = getattr(belief, "scheduling_time", "") or ""
    name = getattr(belief, "scheduling_name", "") or ""
    if day and time_ and name:
        return SchedulingState.CONFIRM
    if day and time_ and not name:
        return SchedulingState.NEED_NAME
    if day and not time_:
        return SchedulingState.NEED_TIME
    if getattr(belief, "pending_scheduling", False):
        return SchedulingState.NEED_DAY
    return SchedulingState.PROPERTY_SELECTED


def _make_plan(text: str) -> list[dict]:
    """Build a minimal response_plan list from a plain text string."""
    return [{"type": "text", "content": text}]


def _hours_description(windows: dict[int, tuple[int, int]]) -> str:
    """Build a human-readable hours description from windows dict."""
    if not windows:
        return "lunes a sábado de 9:00 a 18:00 hs"
    parts = []
    day_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    for wd, (oh, ch) in sorted(windows.items()):
        parts.append(f"{day_names[wd]} de {oh:02d}:00 a {ch:02d}:00 hs")
    return ", ".join(parts)


# ── Core resolve() ────────────────────────────────────────────────────────────

async def resolve(
    belief,
    user_message: str,
    turn,
    booking_succeeded: bool,
    tool_results: list[str],
    tenant_id,
) -> FSMResult:
    """Deterministic post-engine FSM guard.

    Reads: belief.selected_property_id, scheduling_day, scheduling_time,
           scheduling_name, awaiting, scheduling_loop_count, pending_scheduling,
           turn.action, turn.missing_slot, turn.intent.
    Writes: belief.awaiting, scheduling_loop_count, scheduling_day/time/name,
            pending_scheduling (all guarded by try/except on belief mutations).

    Returns FSMResult. Never raises.
    """
    try:
        return await _resolve_impl(
            belief, user_message, turn, booking_succeeded, tool_results, tenant_id
        )
    except Exception as exc:
        logger.warning("[scheduling.fsm] resolve() error (no-op): {}", exc)
        current_state = _derive_state(belief)
        return FSMResult(
            response_plan=None,
            booking_succeeded=booking_succeeded,
            override=False,
            next_state=current_state,
            tools_add=[],
        )


async def _resolve_impl(
    belief,
    user_message: str,
    turn,
    booking_succeeded: bool,
    tool_results: list[str],
    tenant_id,
) -> FSMResult:
    """Inner implementation — may raise (caught by resolve())."""
    msg = user_message or ""
    action = getattr(turn, "action", None)
    missing_slot = getattr(turn, "missing_slot", None)
    turn_intent = getattr(turn, "intent", None)

    current_state = _derive_state(belief)

    # ── T-1: Booking succeeded → booked state ────────────────────────────────
    if booking_succeeded:
        try:
            belief.awaiting = None
            belief.pending_scheduling = False
            belief.scheduling_loop_count = 0
        except Exception:
            pass
        return FSMResult(
            response_plan=None,  # let real confirmation through
            booking_succeeded=True,
            override=False,
            next_state=SchedulingState.BOOKED,
            tools_add=[],
        )

    # ── T-2: Explicit exit cue ────────────────────────────────────────────────
    if _is_exit(msg) and current_state not in (SchedulingState.IDLE, SchedulingState.PROPERTY_SELECTED):
        try:
            belief.awaiting = None
            belief.pending_scheduling = False
            belief.scheduling_day = ""
            belief.scheduling_time = ""
            belief.scheduling_name = ""
            belief.scheduling_loop_count = 0
        except Exception:
            pass
        return FSMResult(
            response_plan=None,
            booking_succeeded=False,
            override=False,
            next_state=SchedulingState.IDLE,
            tools_add=[],
        )

    # ── T-3: Mid-flow intent interruption (topic switch while pending) ────────
    # If pending_scheduling is True but this turn's intent is NOT scheduling,
    # preserve the scheduling context; no FSM override.
    if (
        getattr(belief, "pending_scheduling", False)
        and turn_intent is not None
        and turn_intent not in ("scheduling",)
        and current_state not in (SchedulingState.IDLE, SchedulingState.PROPERTY_SELECTED)
    ):
        # Answer the off-topic question; FSM does nothing
        return FSMResult(
            response_plan=None,
            booking_succeeded=False,
            override=False,
            next_state=current_state,
            tools_add=[],
        )

    # ── T-4: Slot rejection cue (ese día no puedo / no me viene el…) ─────────
    if _is_slot_rejection(msg) and current_state in (
        SchedulingState.NEED_DAY, SchedulingState.NEED_TIME
    ):
        # Load business hours for the helpful reply
        from app.routers.v3.scheduling.utils import load_tenant_hours

        windows, _ = await load_tenant_hours(tenant_id)
        hours_desc = _hours_description(windows)

        if current_state == SchedulingState.NEED_DAY:
            try:
                belief.scheduling_day = ""
                belief.awaiting = "scheduling_day"
            except Exception:
                pass
            plan_text = (
                f"Sin problema. ¿Qué día te vendría mejor? "
                f"Atendemos {hours_desc}."
            )
        else:  # NEED_TIME
            try:
                belief.scheduling_time = ""
                belief.awaiting = "scheduling_time"
            except Exception:
                pass
            plan_text = (
                f"Claro, sin problema. ¿Qué horario te queda bien? "
                f"Atendemos {hours_desc}."
            )
        return FSMResult(
            response_plan=_make_plan(plan_text),
            booking_succeeded=False,
            override=True,
            next_state=current_state,
            tools_add=[],
        )

    # ── T-5: Name correction ──────────────────────────────────────────────────
    if _is_name_correction(msg) and current_state == SchedulingState.NEED_NAME:
        corrected = _extract_name_from_correction(msg)
        if corrected:
            try:
                belief.scheduling_name = corrected
            except Exception:
                pass
        return FSMResult(
            response_plan=None,  # let engine handle the response
            booking_succeeded=False,
            override=False,
            next_state=SchedulingState.NEED_NAME,
            tools_add=[],
        )

    # ── T-6: Loop detection (same slot asked twice with no new info) ──────────
    # The engine is missing the same slot as last turn AND we're in need_* state.
    # We only increment if missing_slot is the same as the current awaiting slot.
    loop_count = getattr(belief, "scheduling_loop_count", 0)
    current_awaiting = getattr(belief, "awaiting", None)

    if (
        missing_slot is not None
        and missing_slot == current_awaiting
        and current_state in (
            SchedulingState.NEED_DAY,
            SchedulingState.NEED_TIME,
            SchedulingState.NEED_NAME,
        )
    ):
        new_loop_count = loop_count + 1
        try:
            belief.scheduling_loop_count = new_loop_count
        except Exception:
            new_loop_count = loop_count + 1

        if new_loop_count > LOOP_MAX:
            # Handoff escalation
            try:
                belief.awaiting = None
                belief.pending_scheduling = False
                belief.scheduling_loop_count = 0
            except Exception:
                pass
            handoff_plan = _make_plan(
                "Parece que tenemos dificultades para coordinar la visita. "
                "Te voy a conectar con uno de nuestros asesores para que te ayude. "
                "¡Gracias por tu paciencia!"
            )
            return FSMResult(
                response_plan=handoff_plan,
                booking_succeeded=False,
                override=True,
                next_state=SchedulingState.HANDOFF,
                tools_add=[],
            )

    # ── T-7: Confirm state pre-check (availability guard) ────────────────────
    # When action==book_step and day+time+name are all set, check availability
    # BEFORE allowing the engine to call schedule_visit.
    if (
        action == "book_step"
        and current_state == SchedulingState.CONFIRM
        and not booking_succeeded  # booking hasn't happened yet
    ):
        day = getattr(belief, "scheduling_day", "") or ""
        time_ = getattr(belief, "scheduling_time", "") or ""
        prop_id = getattr(belief, "selected_property_id", None)

        if day and time_ and prop_id:
            from app.routers.v3.scheduling.utils import parse_day_time_for_tenant
            from app.routers.v3.scheduling.availability import check_availability

            proposed_dt = await parse_day_time_for_tenant(day, time_, tenant_id)
            if proposed_dt is not None:
                avail = await check_availability(prop_id, proposed_dt, tenant_id)
                if not avail["available"]:
                    # Slot is taken — ask for a new time
                    suggestions = avail.get("suggestions", [])
                    try:
                        belief.scheduling_time = ""
                        belief.awaiting = "scheduling_time"
                    except Exception:
                        pass

                    if suggestions:
                        sugg_lines = [
                            f"- {s.get('formatted', str(s))}" for s in suggestions[:3]
                        ]
                        plan_text = (
                            "Ese horario ya está ocupado. "
                            "Estos horarios están disponibles:\n"
                            + "\n".join(sugg_lines)
                            + "\n¿Cuál te viene bien?"
                        )
                    else:
                        plan_text = (
                            "Ese horario no está disponible. "
                            "¿Qué otro horario te conviene?"
                        )
                    return FSMResult(
                        response_plan=_make_plan(plan_text),
                        booking_succeeded=False,
                        override=True,
                        next_state=SchedulingState.NEED_TIME,
                        tools_add=[],
                    )

    # ── T-8: Mark pending_scheduling when scheduling intent starts ────────────
    # If engine is in scheduling mode and not already pending, set the flag.
    if turn_intent == "scheduling" and action in ("book_step", "clarify"):
        try:
            if not getattr(belief, "pending_scheduling", False):
                belief.pending_scheduling = True
        except Exception:
            pass

    # ── No FSM override needed ────────────────────────────────────────────────
    next_state = _derive_state(belief)
    return FSMResult(
        response_plan=None,
        booking_succeeded=booking_succeeded,
        override=False,
        next_state=next_state,
        tools_add=[],
    )
