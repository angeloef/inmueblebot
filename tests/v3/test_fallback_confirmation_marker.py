"""Plan #5: schedule_visit fallback confirmation must emit the CONFIRMED marker.

When create_appointment returns success without an appointment object, the
fallback confirmation used to omit the <!--CONFIRMED:--> marker, so the engine's
booking_succeeded stayed False and Path 0b discarded the confirmation — the user
got "estoy recopilando los detalles" after a REAL booking.

Exercises the pure helper _fallback_confirmation (offline) and confirms the engine
treats its output as a successful booking.
"""

import unittest
from datetime import datetime

import pytz

from app.tools.v2.schedule_visit import _fallback_confirmation
from app.routers.v3.engine import _BOOKING_SUCCESS_MARKER

_AR = pytz.timezone("America/Argentina/Buenos_Aires")


class TestFallbackConfirmationMarker(unittest.TestCase):

    def _build(self, **over):
        defaults = dict(
            property_id=7,
            prop_title="Depto Centro",
            prop_address="San Martín 100",
            nombre="Ana López",
            dia="jueves",
            horario="16:00",
            consulta="",
            roll_note="",
            start_datetime=_AR.localize(datetime(2026, 6, 18, 16, 0)),
        )
        defaults.update(over)
        return _fallback_confirmation(**defaults)

    def test_marker_present(self):
        text = self._build()
        self.assertIn(_BOOKING_SUCCESS_MARKER, text)

    def test_marker_uses_parsed_datetime_not_raw_strings(self):
        text = self._build(dia="jueves", horario="las 4 de la tarde")
        # Marker carries the canonical YYYY-MM-DD HH:MM from start_datetime, not "las 4..."
        self.assertIn("<!--CONFIRMED:2026-06-18 16:00-->", text)

    def test_engine_detects_booking_success(self):
        """The engine's booking-success check keys on this marker substring."""
        text = self._build()
        self.assertIn(_BOOKING_SUCCESS_MARKER, text)
        self.assertTrue(text.find(_BOOKING_SUCCESS_MARKER) > 0)

    def test_human_readable_confirmation_intact(self):
        text = self._build()
        self.assertIn("¡Visita agendada!", text)
        self.assertIn("Ana López", text)
        self.assertIn("Depto Centro", text)

    def test_roll_note_prepended_when_present(self):
        text = self._build(roll_note="Esa fecha ya pasó, agendé el próximo jueves.")
        self.assertTrue(text.startswith("Esa fecha ya pasó"))
        self.assertIn(_BOOKING_SUCCESS_MARKER, text)


if __name__ == "__main__":
    unittest.main()
