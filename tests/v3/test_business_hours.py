"""Unit tests for scheduling/utils.py — business-hours parsing + load_tenant_hours.

Tests: parse_business_hours (EN/ES, malformed→None),
       is_within_business_hours (in/out, Sunday closed, Sat 13:00 boundary),
       load_tenant_hours degradation when get_tenant→None (monkeypatched).

Orchestrator runs these; do not execute manually during Phase 4 implementation.
"""

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import app.services.tenant_service  # noqa: F401 — ensure submodule loaded so patch target resolves

from app.routers.v3.scheduling.utils import (
    DEFAULT_TZ,
    _DEFAULT_WINDOWS,
    describe_hours,
    is_within_business_hours,
    load_tenant_hours,
    parse_business_hours,
    parse_business_hours_es,
)


class TestParseBusinessHoursEs(unittest.TestCase):
    def test_faq_style_phrasing(self):
        text = ("Nuestro horario de atención es de lunes a viernes de 9:00 a 18:00 hs, "
                "y los sábados de 9:00 a 13:00 hs.")
        windows = parse_business_hours_es(text)
        self.assertIsNotNone(windows)
        for wd in range(0, 5):
            self.assertEqual(windows[wd], (9, 18))
        self.assertEqual(windows[5], (9, 13))
        self.assertNotIn(6, windows)

    def test_other_city_hours(self):
        # A tenant in another part of the country with different hours.
        windows = parse_business_hours_es("Atendemos de lunes a sábado de 8 a 20 hs")
        self.assertIsNotNone(windows)
        self.assertEqual(windows[0], (8, 20))
        self.assertEqual(windows[5], (8, 20))

    def test_unparseable_returns_none(self):
        self.assertIsNone(parse_business_hours_es("consultanos por WhatsApp cuando quieras"))


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDescribeHours(unittest.TestCase):
    def test_groups_consecutive_equal_windows(self):
        # Default windows: Mon-Fri 9-18, Sat 9-13 → grouped, not enumerated per-day.
        desc = describe_hours(_DEFAULT_WINDOWS)
        self.assertIn("lunes a viernes de 09:00 a 18:00 hs", desc)
        self.assertIn("sábado de 09:00 a 13:00 hs", desc)
        self.assertNotIn("martes", desc)  # grouped away

    def test_empty_windows_falls_back_to_default_text(self):
        self.assertIn("lunes a viernes", describe_hours({}))


class TestParseBusinessHours(unittest.TestCase):

    # ── Valid English formats ─────────────────────────────────────────────────

    def test_en_mon_fri_sat(self):
        windows = parse_business_hours("Mon-Fri 09:00-18:00, Sat 09:00-13:00")
        self.assertIsNotNone(windows)
        # Mon through Fri should be (9, 18)
        for wd in range(0, 5):
            self.assertEqual(windows[wd], (9, 18), f"weekday {wd} should be 09-18")
        # Saturday (5) should be (9, 13)
        self.assertEqual(windows[5], (9, 13))
        # Sunday (6) should be absent
        self.assertNotIn(6, windows)

    def test_en_single_day(self):
        windows = parse_business_hours("Mon 09:00-12:00")
        self.assertIsNotNone(windows)
        self.assertEqual(windows[0], (9, 12))

    # ── Valid Spanish formats ─────────────────────────────────────────────────

    def test_es_lun_vie_sab(self):
        windows = parse_business_hours("Lun-Vie 09:00-18:00, Sáb 09:00-13:00")
        self.assertIsNotNone(windows)
        for wd in range(0, 5):
            self.assertEqual(windows[wd], (9, 18))
        self.assertEqual(windows[5], (9, 13))
        self.assertNotIn(6, windows)

    def test_es_lun_vie_no_accent(self):
        windows = parse_business_hours("Lun-Vie 08:00-20:00")
        self.assertIsNotNone(windows)
        for wd in range(0, 5):
            self.assertEqual(windows[wd], (8, 20))

    # ── Malformed → None ─────────────────────────────────────────────────────

    def test_none_input(self):
        self.assertIsNone(parse_business_hours(None))

    def test_empty_string(self):
        self.assertIsNone(parse_business_hours(""))

    def test_no_times(self):
        self.assertIsNone(parse_business_hours("Monday to Friday"))

    def test_garbage_string(self):
        self.assertIsNone(parse_business_hours("xxxxxxxxx"))

    def test_single_time_only(self):
        # Only one time found — clause needs two
        self.assertIsNone(parse_business_hours("Mon 09:00"))


class TestIsWithinBusinessHours(unittest.TestCase):

    _WINDOWS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}

    def test_in_hours_monday_10am(self):
        # Monday (weekday 0) at 10:00 — should be True
        dt = datetime(2026, 6, 1, 10, 0)  # 2026-06-01 is a Monday
        self.assertTrue(is_within_business_hours(dt, self._WINDOWS))

    def test_out_of_hours_monday_8am(self):
        dt = datetime(2026, 6, 1, 8, 0)
        self.assertFalse(is_within_business_hours(dt, self._WINDOWS))

    def test_out_of_hours_monday_18pm(self):
        # 18:00 is close_h, so out of range (open_h <= hour < close_h)
        dt = datetime(2026, 6, 1, 18, 0)
        self.assertFalse(is_within_business_hours(dt, self._WINDOWS))

    def test_saturday_in_hours_12pm(self):
        # Saturday (weekday 5) at 12:00 — (9, 13) → True
        dt = datetime(2026, 6, 6, 12, 0)  # 2026-06-06 is a Saturday
        self.assertTrue(is_within_business_hours(dt, self._WINDOWS))

    def test_saturday_boundary_13pm(self):
        # Saturday at 13:00 — boundary, should be False (9 <= 13 < 13 is False)
        dt = datetime(2026, 6, 6, 13, 0)
        self.assertFalse(is_within_business_hours(dt, self._WINDOWS))

    def test_sunday_closed(self):
        # Sunday (weekday 6) is not in windows
        dt = datetime(2026, 6, 7, 10, 0)  # 2026-06-07 is a Sunday
        self.assertFalse(is_within_business_hours(dt, self._WINDOWS))

    def test_fail_open_on_exception(self):
        # Passing something invalid should fail-open (True)
        result = is_within_business_hours(None, {})  # type: ignore[arg-type]
        self.assertTrue(result)


class TestLoadTenantHours(unittest.TestCase):

    def test_tenant_none_returns_defaults(self):
        """When tenant_id is None → DEFAULT_WINDOWS + DEFAULT_TZ."""
        windows, tz = _run(load_tenant_hours(None))
        self.assertEqual(windows, _DEFAULT_WINDOWS)
        self.assertEqual(tz, DEFAULT_TZ)

    def test_get_tenant_returns_none_returns_defaults(self):
        """When get_tenant() returns None → DEFAULT_WINDOWS + DEFAULT_TZ."""
        import uuid
        fake_tid = uuid.uuid4()

        with patch(
            "app.services.tenant_service.get_tenant",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.routers.v3.scheduling.utils._load_hours_from_faq",
            new=AsyncMock(return_value=None),
        ):
            # re-import to pick up the patch
            from importlib import import_module
            utils_mod = import_module("app.routers.v3.scheduling.utils")
            windows, tz = _run(utils_mod.load_tenant_hours(fake_tid))

        self.assertEqual(windows, _DEFAULT_WINDOWS)
        self.assertEqual(tz, DEFAULT_TZ)

    def test_tenant_with_valid_hours_and_tz(self):
        """When tenant has valid business_hours + tz, use them."""
        import uuid
        from types import SimpleNamespace

        fake_tenant = SimpleNamespace(
            business_hours="Mon-Fri 09:00-18:00, Sat 09:00-13:00",
            timezone="America/Buenos_Aires",
        )

        with patch(
            "app.services.tenant_service.get_tenant",
            new=AsyncMock(return_value=fake_tenant),
        ), patch(
            "app.routers.v3.scheduling.utils._load_hours_from_faq",
            new=AsyncMock(return_value=None),
        ):
            from importlib import import_module
            utils_mod = import_module("app.routers.v3.scheduling.utils")
            windows, tz = _run(utils_mod.load_tenant_hours(uuid.uuid4()))

        self.assertIn(0, windows)
        self.assertEqual(windows[0], (9, 18))

    def test_tenant_with_null_hours_uses_defaults(self):
        """When tenant has null business_hours, fall back to DEFAULT_WINDOWS."""
        import uuid
        from types import SimpleNamespace

        fake_tenant = SimpleNamespace(
            business_hours=None,
            timezone="America/Argentina/Cordoba",
        )

        with patch(
            "app.services.tenant_service.get_tenant",
            new=AsyncMock(return_value=fake_tenant),
        ), patch(
            "app.routers.v3.scheduling.utils._load_hours_from_faq",
            new=AsyncMock(return_value=None),
        ):
            from importlib import import_module
            utils_mod = import_module("app.routers.v3.scheduling.utils")
            windows, tz = _run(utils_mod.load_tenant_hours(uuid.uuid4()))

        self.assertEqual(windows, _DEFAULT_WINDOWS)
        self.assertEqual(tz, "America/Argentina/Cordoba")


if __name__ == "__main__":
    unittest.main()
