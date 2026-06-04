"""Unit tests for scheduling/fsm.py — FSM transition table.

Tests:
  - Slot rejection stays in current state + offers alternatives
  - Name correction updates belief.scheduling_name, stays need_name
  - Loop > LOOP_MAX (3) → handoff override
  - booking_succeeded=True → booked state, awaiting=None cleared
  - Explicit exit cue → clears scheduling fields

Orchestrator runs these; do not execute manually during Phase 4 implementation.
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers.v3.scheduling.fsm import (
    LOOP_MAX,
    FSMResult,
    SchedulingState,
    resolve,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_belief(
    *,
    selected_property_id=42,
    awaiting="scheduling_time",
    scheduling_day="viernes",
    scheduling_time="",
    scheduling_name="",
    scheduling_loop_count=0,
    pending_scheduling=True,
):
    b = SimpleNamespace(
        selected_property_id=selected_property_id,
        awaiting=awaiting,
        scheduling_day=scheduling_day,
        scheduling_time=scheduling_time,
        scheduling_name=scheduling_name,
        scheduling_loop_count=scheduling_loop_count,
        pending_scheduling=pending_scheduling,
    )
    return b


def _make_turn(action="book_step", missing_slot=None, intent="scheduling"):
    return SimpleNamespace(
        action=action,
        missing_slot=missing_slot,
        intent=intent,
        tool_calls=[],
        confidence=0.9,
        selected_property_id=None,
        response_plan=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFSMBookingSucceeded(unittest.TestCase):
    """booking_succeeded=True → booked state, awaiting/pending cleared."""

    def test_booking_succeeded_clears_awaiting(self):
        belief = _make_belief(awaiting="scheduling_confirm", scheduling_loop_count=2)
        turn = _make_turn(action="book_step")

        result = _run(resolve(belief, "confirmar", turn, booking_succeeded=True, tool_results=[], tenant_id=None))

        self.assertEqual(result.next_state, SchedulingState.BOOKED)
        self.assertTrue(result.booking_succeeded)
        self.assertFalse(result.override, "No override on real booking — let confirmation through")
        self.assertIsNone(belief.awaiting)
        self.assertFalse(belief.pending_scheduling)
        self.assertEqual(belief.scheduling_loop_count, 0)


class TestFSMExitCue(unittest.TestCase):
    """Explicit exit cue clears scheduling fields."""

    def test_chau_clears_scheduling_fields(self):
        belief = _make_belief(
            awaiting="scheduling_time",
            scheduling_day="viernes",
            scheduling_name="Juan",
        )
        turn = _make_turn(action="clarify")

        result = _run(resolve(belief, "chau, gracias", turn, booking_succeeded=False, tool_results=[], tenant_id=None))

        self.assertEqual(result.next_state, SchedulingState.IDLE)
        self.assertFalse(result.override)
        self.assertIsNone(belief.awaiting)
        self.assertFalse(belief.pending_scheduling)
        self.assertEqual(belief.scheduling_day, "")

    def test_no_me_interesa_clears(self):
        belief = _make_belief(awaiting="scheduling_day")
        turn = _make_turn(action="clarify")

        result = _run(resolve(belief, "no me interesa", turn, booking_succeeded=False, tool_results=[], tenant_id=None))

        self.assertEqual(result.next_state, SchedulingState.IDLE)
        self.assertEqual(belief.scheduling_day, "")


class TestFSMSlotRejection(unittest.TestCase):
    """Slot rejection stays in current state + offers alternatives."""

    def test_ese_dia_no_puedo_stays_need_day(self):
        belief = _make_belief(
            awaiting="scheduling_day",
            scheduling_day="",
        )
        turn = _make_turn(action="book_step", missing_slot="scheduling_day")

        # Patch load_tenant_hours to avoid DB
        with patch(
            "app.routers.v3.scheduling.utils.load_tenant_hours",
            new=AsyncMock(return_value=({0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}, "America/Argentina/Cordoba")),
        ):
            result = _run(resolve(
                belief, "ese día no puedo", turn,
                booking_succeeded=False, tool_results=[], tenant_id=None
            ))

        self.assertTrue(result.override)
        self.assertIsNotNone(result.response_plan)
        self.assertEqual(result.next_state, SchedulingState.NEED_DAY)
        # scheduling_day should be reset
        self.assertEqual(belief.scheduling_day, "")

    def test_no_me_viene_ese_horario_stays_need_time(self):
        belief = _make_belief(
            awaiting="scheduling_time",
            scheduling_time="10:00",
        )
        turn = _make_turn(action="book_step", missing_slot="scheduling_time")

        with patch(
            "app.routers.v3.scheduling.utils.load_tenant_hours",
            new=AsyncMock(return_value=({0: (9, 18)}, "America/Argentina/Cordoba")),
        ):
            result = _run(resolve(
                belief, "no me viene el horario ese, busco otro", turn,
                booking_succeeded=False, tool_results=[], tenant_id=None
            ))

        self.assertTrue(result.override)
        self.assertEqual(result.next_state, SchedulingState.NEED_TIME)
        self.assertEqual(belief.scheduling_time, "")


class TestFSMNameCorrection(unittest.TestCase):
    """Name correction updates belief.scheduling_name, stays need_name."""

    def test_me_llamo_updates_name(self):
        belief = _make_belief(
            awaiting="scheduling_name",
            scheduling_name="Pedro",
        )
        turn = _make_turn(action="book_step", missing_slot="scheduling_name")

        result = _run(resolve(
            belief, "me llamo Carlos", turn,
            booking_succeeded=False, tool_results=[], tenant_id=None
        ))

        self.assertFalse(result.override, "Name correction: no override needed")
        self.assertEqual(result.next_state, SchedulingState.NEED_NAME)
        # Belief name should be updated
        self.assertEqual(belief.scheduling_name, "Carlos")


class TestFSMLoopEscalation(unittest.TestCase):
    """Loop > LOOP_MAX triggers handoff override."""

    def test_loop_beyond_max_triggers_handoff(self):
        belief = _make_belief(
            awaiting="scheduling_time",
            scheduling_loop_count=LOOP_MAX,  # already at max
        )
        turn = _make_turn(action="book_step", missing_slot="scheduling_time")

        result = _run(resolve(
            belief, "no sé a qué hora", turn,
            booking_succeeded=False, tool_results=[], tenant_id=None
        ))

        self.assertEqual(result.next_state, SchedulingState.HANDOFF)
        self.assertTrue(result.override)
        self.assertIsNotNone(result.response_plan)
        # Verify plan contains some human escalation text
        plan_text = " ".join(p.get("content", "") for p in result.response_plan if isinstance(p, dict))
        self.assertTrue(
            "asesor" in plan_text.lower() or "agente" in plan_text.lower() or "conectar" in plan_text.lower(),
            f"Handoff plan should mention asesor/agente: {plan_text!r}"
        )

    def test_loop_at_max_increments_then_triggers(self):
        """Loop_count == LOOP_MAX: increment to LOOP_MAX+1 → handoff."""
        belief = _make_belief(
            awaiting="scheduling_day",
            scheduling_loop_count=LOOP_MAX,
        )
        turn = _make_turn(action="book_step", missing_slot="scheduling_day")

        result = _run(resolve(
            belief, "no sé qué día", turn,
            booking_succeeded=False, tool_results=[], tenant_id=None
        ))

        self.assertEqual(result.next_state, SchedulingState.HANDOFF)

    def test_loop_below_max_does_not_trigger_handoff(self):
        """Loop_count < LOOP_MAX: increments but no handoff."""
        belief = _make_belief(
            awaiting="scheduling_time",
            scheduling_loop_count=1,
        )
        turn = _make_turn(action="book_step", missing_slot="scheduling_time")

        result = _run(resolve(
            belief, "no sé", turn,
            booking_succeeded=False, tool_results=[], tenant_id=None
        ))

        self.assertNotEqual(result.next_state, SchedulingState.HANDOFF)
        self.assertFalse(result.override)


class TestFSMNeverRaises(unittest.TestCase):
    """resolve() must never raise regardless of input."""

    def test_none_belief(self):
        """Passing None as belief should not raise — returns FSMResult."""
        turn = _make_turn()
        # Should not raise — catches all exceptions
        result = _run(resolve(None, "cualquier mensaje", turn, False, [], None))
        self.assertIsInstance(result, FSMResult)

    def test_none_turn(self):
        """Passing None as turn should not raise."""
        belief = _make_belief()
        result = _run(resolve(belief, "hola", None, False, [], None))
        self.assertIsInstance(result, FSMResult)


if __name__ == "__main__":
    unittest.main()
