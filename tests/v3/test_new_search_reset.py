"""Plan #3: reset selected_property_id + scheduling slots on a new search.

A fresh search must invalidate the prior selection and any in-flight scheduling
slots so a property-scoped follow-up ("mostrame fotos") can't backfill the OLD
property and a half-finished booking can't leak across searches. The person's
name (scheduling_name) is preserved.

All offline — exercises the pure helper _apply_new_search_reset.
"""

import unittest

from app.routers.v3.engine import _apply_new_search_reset


class _StubBelief:
    def __init__(self):
        self.selected_property_id = 7
        self.awaiting = "scheduling_time"
        self.pending_scheduling = True
        self.scheduling_day = "jueves"
        self.scheduling_time = "16:00"
        self.scheduling_name = "Ana López"


class _StubTurn:
    def __init__(self, selected_property_id=None):
        self.selected_property_id = selected_property_id


class TestNewSearchReset(unittest.TestCase):

    def test_clears_stale_selection(self):
        b = _StubBelief()
        _apply_new_search_reset(b, _StubTurn(selected_property_id=None))
        self.assertIsNone(b.selected_property_id)

    def test_clears_inflight_scheduling_slots(self):
        b = _StubBelief()
        _apply_new_search_reset(b, _StubTurn())
        self.assertIsNone(b.awaiting)
        self.assertFalse(b.pending_scheduling)
        self.assertEqual(b.scheduling_day, "")
        self.assertEqual(b.scheduling_time, "")

    def test_preserves_name(self):
        b = _StubBelief()
        _apply_new_search_reset(b, _StubTurn())
        self.assertEqual(b.scheduling_name, "Ana López")

    def test_does_not_touch_slots_when_not_scheduling(self):
        """If the user wasn't mid-booking, scheduling fields are left as-is."""
        b = _StubBelief()
        b.awaiting = None
        b.pending_scheduling = False
        b.scheduling_day = ""
        b.scheduling_time = ""
        _apply_new_search_reset(b, _StubTurn())
        # selection still cleared, slots untouched (already empty)
        self.assertIsNone(b.selected_property_id)
        self.assertIsNone(b.awaiting)

    def test_honours_explicit_new_selection(self):
        """If the engine emitted a selection THIS turn, it wins over a bare clear."""
        b = _StubBelief()
        _apply_new_search_reset(b, _StubTurn(selected_property_id=12))
        self.assertEqual(b.selected_property_id, 12)

    def test_non_scheduling_awaiting_preserved(self):
        """A non-scheduling 'awaiting' (e.g. a clarify) must not be wiped."""
        b = _StubBelief()
        b.awaiting = "operation"
        _apply_new_search_reset(b, _StubTurn())
        self.assertEqual(b.awaiting, "operation")


if __name__ == "__main__":
    unittest.main()
