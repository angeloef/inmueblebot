"""Plan #22: FSM T-7 availability pre-check is live now that #10 populates slots.

T-7 reads belief.scheduling_day/time, which the engine path never wrote before #10,
so the CONFIRM-state availability guard was dead. With slots persisted it can reject
a taken slot BEFORE schedule_visit runs. These tests stub the date parser + the
availability check and assert the guard fires (and stays out of the way when free).

Offline — the two collaborators are patched; no DB.
"""

import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers.v3.scheduling.fsm import SchedulingState, resolve


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _confirm_belief():
    """A belief in CONFIRM state: property + day + time + name all set."""
    return SimpleNamespace(
        selected_property_id=7,
        awaiting="scheduling_confirm",
        scheduling_day="jueves",
        scheduling_time="15:00",
        scheduling_name="Ana López",
        scheduling_loop_count=0,
        pending_scheduling=True,
    )


def _turn():
    return SimpleNamespace(
        action="book_step", missing_slot=None, intent="scheduling",
        tool_calls=[], confidence=0.9, selected_property_id=None, response_plan=[],
    )


_DT = datetime(2026, 6, 18, 15, 0)


class TestFsmAvailabilityPrecheck(unittest.TestCase):

    def test_taken_slot_overrides_and_reasks_time(self):
        belief = _confirm_belief()
        taken = {"available": False, "suggestions": [{"formatted": "viernes 16:00"}]}
        with patch("app.routers.v3.scheduling.utils.parse_day_time_for_tenant",
                   new=AsyncMock(return_value=_DT)), \
             patch("app.routers.v3.scheduling.availability.check_availability",
                   new=AsyncMock(return_value=taken)):
            result = _run(resolve(belief, "dale", _turn(),
                                  booking_succeeded=False, tool_results=[], tenant_id=None))
        self.assertTrue(result.override)
        self.assertEqual(result.next_state, SchedulingState.NEED_TIME)
        self.assertIn("ocupado", result.response_plan[0]["content"])
        self.assertEqual(belief.awaiting, "scheduling_time")
        self.assertEqual(belief.scheduling_time, "")  # cleared so the user re-picks

    def test_available_slot_does_not_override(self):
        belief = _confirm_belief()
        with patch("app.routers.v3.scheduling.utils.parse_day_time_for_tenant",
                   new=AsyncMock(return_value=_DT)), \
             patch("app.routers.v3.scheduling.availability.check_availability",
                   new=AsyncMock(return_value={"available": True, "suggestions": []})):
            result = _run(resolve(belief, "dale", _turn(),
                                  booking_succeeded=False, tool_results=[], tenant_id=None))
        self.assertFalse(result.override)
        self.assertEqual(belief.scheduling_time, "15:00")  # untouched

    def test_precheck_skipped_when_already_booked(self):
        belief = _confirm_belief()
        chk = AsyncMock(return_value={"available": False, "suggestions": []})
        with patch("app.routers.v3.scheduling.availability.check_availability", new=chk):
            result = _run(resolve(belief, "dale", _turn(),
                                  booking_succeeded=True, tool_results=[], tenant_id=None))
        chk.assert_not_called()
        self.assertTrue(result.booking_succeeded)


if __name__ == "__main__":
    unittest.main()
