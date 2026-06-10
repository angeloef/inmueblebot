"""Plan #13: clear a stale scheduling `awaiting` after the user moves on.

`awaiting` has no TTL, so an abandoned booking kept telling the LLM (via [ESTADO])
that it was waiting for a slot. The clear fires only after TWO consecutive
non-scheduling turns, so a single FAQ interruption mid-booking does not reset it.

All offline — exercises _clear_stale_scheduling_awaiting directly.
"""

import unittest
from types import SimpleNamespace

from app.routers.v3.engine import _clear_stale_scheduling_awaiting


def _belief(awaiting="scheduling_day", pending=True):
    return SimpleNamespace(awaiting=awaiting, pending_scheduling=pending)


def _turn(intent):
    return SimpleNamespace(intent=intent)


class TestStaleAwaitingClear(unittest.TestCase):

    def test_two_off_topic_turns_clear_awaiting(self):
        b = _belief()
        _clear_stale_scheduling_awaiting(b, _turn("search"), prev_last_intent="search")
        self.assertIsNone(b.awaiting)
        self.assertFalse(b.pending_scheduling)

    def test_single_interruption_preserves_awaiting(self):
        """One FAQ turn (previous turn WAS scheduling) must not clear the flow."""
        b = _belief()
        _clear_stale_scheduling_awaiting(b, _turn("knowledge"), prev_last_intent="scheduling")
        self.assertEqual(b.awaiting, "scheduling_day")
        self.assertTrue(b.pending_scheduling)

    def test_scheduling_turn_never_clears(self):
        b = _belief()
        _clear_stale_scheduling_awaiting(b, _turn("scheduling"), prev_last_intent="search")
        self.assertEqual(b.awaiting, "scheduling_day")

    def test_non_scheduling_awaiting_untouched(self):
        b = _belief(awaiting="property_selection")
        _clear_stale_scheduling_awaiting(b, _turn("search"), prev_last_intent="search")
        self.assertEqual(b.awaiting, "property_selection")

    def test_no_prior_intent_does_not_clear(self):
        b = _belief()
        _clear_stale_scheduling_awaiting(b, _turn("search"), prev_last_intent=None)
        self.assertEqual(b.awaiting, "scheduling_day")

    def test_none_awaiting_is_safe(self):
        b = _belief(awaiting=None, pending=False)
        _clear_stale_scheduling_awaiting(b, _turn("search"), prev_last_intent="search")
        self.assertIsNone(b.awaiting)


if __name__ == "__main__":
    unittest.main()
