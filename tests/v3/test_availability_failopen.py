"""Plan #16: availability fail-open emits a WARNING metric line.

The availability check fails open (returns available=True) on any DB/calendar
error — a deliberate product call, but a double-booking risk that must be
observable. emit_availability_failopen logs a selectable AVAILABILITY_FAILOPEN
marker so an alert can fire on a sustained rate.

Offline — exercises the metric emitter directly.
"""

import json
import unittest

from loguru import logger

from app.core import turn_metrics


class _LogCapture:
    def __enter__(self):
        self.messages: list[str] = []
        self._sink_id = logger.add(lambda m: self.messages.append(str(m)), level="WARNING")
        return self

    def __exit__(self, *exc):
        logger.remove(self._sink_id)
        return False


class TestAvailabilityFailopenMetric(unittest.TestCase):

    def test_emits_marker_with_stage_and_property(self):
        with _LogCapture() as cap:
            turn_metrics.emit_availability_failopen(stage="db", property_id=7, reason="boom")
        joined = "\n".join(cap.messages)
        self.assertIn("AVAILABILITY_FAILOPEN", joined)
        self.assertIn('"stage": "db"', joined)
        self.assertIn('"property_id": 7', joined)

    def test_calendar_stage_distinguished(self):
        with _LogCapture() as cap:
            turn_metrics.emit_availability_failopen(stage="calendar", property_id=9, reason="x")
        self.assertTrue(any('"stage": "calendar"' in m for m in cap.messages))

    def test_reason_truncated(self):
        with _LogCapture() as cap:
            turn_metrics.emit_availability_failopen(stage="db", property_id=1, reason="z" * 500)
        line = next(m for m in cap.messages if "AVAILABILITY_FAILOPEN" in m)
        payload = json.loads(line.split("AVAILABILITY_FAILOPEN", 1)[1].strip())
        self.assertLessEqual(len(payload["reason"]), 200)

    def test_never_raises_on_bad_input(self):
        # Should swallow any serialization issue rather than break a booking turn.
        turn_metrics.emit_availability_failopen(stage="db", property_id=object(), reason="x")


if __name__ == "__main__":
    unittest.main()
