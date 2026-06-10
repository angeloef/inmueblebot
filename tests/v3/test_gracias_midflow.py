"""Plan #11: a polite "gracias" mid-scheduling must not wipe day/time/name.

The FSM exit cue used to include bare "gracias", so "sí, gracias, soy Juan" at
NEED_NAME tripped T-2 and cleared the whole scheduling flow. Now bare "gracias"
only ends the flow when the WHOLE message is a thank-you; strong cues (chau,
no gracias, …) still end it.

All offline — no LLM / DB / Redis.
"""

import asyncio
import unittest
from types import SimpleNamespace

from app.routers.v3.scheduling.fsm import SchedulingState, resolve, _is_exit


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_belief(**over):
    base = dict(
        selected_property_id=42,
        awaiting="scheduling_name",
        scheduling_day="viernes",
        scheduling_time="15:00",
        scheduling_name="",
        scheduling_loop_count=0,
        pending_scheduling=True,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _make_turn(action="clarify", missing_slot="scheduling_name", intent="scheduling"):
    return SimpleNamespace(
        action=action, missing_slot=missing_slot, intent=intent,
        tool_calls=[], confidence=0.9, selected_property_id=None, response_plan=[],
    )


class TestIsExit(unittest.TestCase):

    def test_standalone_gracias_is_exit(self):
        self.assertTrue(_is_exit("gracias"))
        self.assertTrue(_is_exit("muchas gracias"))
        self.assertTrue(_is_exit("  gracias!  "))
        self.assertTrue(_is_exit("mil gracias"))

    def test_gracias_with_name_is_not_exit(self):
        self.assertFalse(_is_exit("sí, gracias, soy Juan"))
        self.assertFalse(_is_exit("gracias, me llamo Ana López"))
        self.assertFalse(_is_exit("dale gracias el viernes a las 15"))

    def test_strong_cues_still_exit(self):
        self.assertTrue(_is_exit("chau"))
        self.assertTrue(_is_exit("no gracias"))
        self.assertTrue(_is_exit("no me interesa"))
        self.assertTrue(_is_exit("mejor busco otra"))


class TestGraciasMidFlow(unittest.TestCase):

    def test_si_gracias_soy_juan_preserves_state(self):
        belief = _make_belief()
        result = _run(resolve(
            belief, "sí, gracias, soy Juan Pérez", _make_turn(),
            booking_succeeded=False, tool_results=[], tenant_id=None,
        ))
        self.assertNotEqual(result.next_state, SchedulingState.IDLE)
        self.assertEqual(belief.scheduling_day, "viernes")
        self.assertEqual(belief.scheduling_time, "15:00")
        self.assertIsNotNone(belief.awaiting)

    def test_standalone_gracias_still_exits(self):
        belief = _make_belief()
        result = _run(resolve(
            belief, "gracias", _make_turn(),
            booking_succeeded=False, tool_results=[], tenant_id=None,
        ))
        self.assertEqual(result.next_state, SchedulingState.IDLE)
        self.assertEqual(belief.scheduling_day, "")


if __name__ == "__main__":
    unittest.main()
