"""Plan #10: persist scheduling day/time/name to belief on the engine path.

The engine path used to write only `awaiting`, never the slot VALUES, so a day
given early in a long booking flow was forgotten once it slid out of the history
window. Two persistence points are covered:
  - _persist_schedule_args: copy a schedule_visit call's dia/horario/nombre.
  - _persist_scheduling_slots_from_message: capture concrete day/time the user gives.

All offline — uses the real regex extractors; no LLM / DB / Redis.
"""

import unittest


class _Belief:
    def __init__(self):
        self.scheduling_day = ""
        self.scheduling_time = ""
        self.scheduling_name = ""


class _Turn:
    def __init__(self, intent):
        self.intent = intent


class TestPersistScheduleArgs(unittest.TestCase):

    def test_full_args_stored(self):
        from app.routers.v3.engine import _persist_schedule_args
        b = _Belief()
        _persist_schedule_args(b, {"property_id": 7, "dia": "jueves", "horario": "15:00", "nombre": "Ana"})
        self.assertEqual(b.scheduling_day, "jueves")
        self.assertEqual(b.scheduling_time, "15:00")
        self.assertEqual(b.scheduling_name, "Ana")

    def test_partial_args_do_not_wipe_existing(self):
        from app.routers.v3.engine import _persist_schedule_args
        b = _Belief()
        b.scheduling_time = "15:00"
        b.scheduling_name = "Ana"
        # A re-emission carrying only the day must not clear the captured time/name.
        _persist_schedule_args(b, {"property_id": 7, "dia": "viernes"})
        self.assertEqual(b.scheduling_day, "viernes")
        self.assertEqual(b.scheduling_time, "15:00")
        self.assertEqual(b.scheduling_name, "Ana")

    def test_empty_strings_ignored(self):
        from app.routers.v3.engine import _persist_schedule_args
        b = _Belief()
        b.scheduling_day = "lunes"
        _persist_schedule_args(b, {"dia": "", "horario": None})
        self.assertEqual(b.scheduling_day, "lunes")


class TestPersistSlotsFromMessage(unittest.TestCase):

    def test_scheduling_turn_captures_day_and_time(self):
        from app.routers.v3.engine import _persist_scheduling_slots_from_message
        b = _Belief()
        _persist_scheduling_slots_from_message(b, _Turn("scheduling"), "el viernes a las 15")
        self.assertEqual(b.scheduling_day, "viernes")
        self.assertEqual(b.scheduling_time, "15:00")

    def test_non_scheduling_turn_is_ignored(self):
        from app.routers.v3.engine import _persist_scheduling_slots_from_message
        b = _Belief()
        _persist_scheduling_slots_from_message(b, _Turn("search"), "el viernes a las 15")
        self.assertEqual(b.scheduling_day, "")
        self.assertEqual(b.scheduling_time, "")

    def test_miss_does_not_clear_existing(self):
        from app.routers.v3.engine import _persist_scheduling_slots_from_message
        b = _Belief()
        b.scheduling_day = "jueves"
        # No concrete day/time in the message → previously captured day preserved.
        _persist_scheduling_slots_from_message(b, _Turn("scheduling"), "sí, dale")
        self.assertEqual(b.scheduling_day, "jueves")

    def test_empty_message_is_safe(self):
        from app.routers.v3.engine import _persist_scheduling_slots_from_message
        b = _Belief()
        _persist_scheduling_slots_from_message(b, _Turn("scheduling"), "")
        self.assertEqual(b.scheduling_day, "")


if __name__ == "__main__":
    unittest.main()
