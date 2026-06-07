"""Unit tests for search_properties pure helpers — Argentine price format and the
progressive-narrowing question logic (manual-test-1 fixes).

These cover the formatting/narrowing decisions without touching the DB.
"""

import unittest

from app.tools.v2.search_properties import (
    _MAX_LIST,
    _format_price_ars,
    _next_filter_question,
)


class TestFormatPriceArs(unittest.TestCase):
    def test_rental_uses_dot_thousands_and_per_month(self):
        self.assertEqual(_format_price_ars(35976, is_rental=True), "$35.976/mes")

    def test_sale_has_no_per_month_suffix(self):
        self.assertEqual(_format_price_ars(22000000, is_rental=False), "$22.000.000")

    def test_no_comma_separators_leak(self):
        # The bug was Python's default ',' thousands separator ($35,976).
        self.assertNotIn(",", _format_price_ars(112017, is_rental=True))


class TestNextFilterQuestion(unittest.TestCase):
    def test_asks_zone_first_when_unknown(self):
        q = _next_filter_question(zona="", presupuesto_max=0, dormitorios=0, count=12)
        self.assertIsNotNone(q)
        self.assertIn("zona", q.lower())

    def test_asks_bedrooms_when_zone_known(self):
        q = _next_filter_question(zona="Oberá", presupuesto_max=0, dormitorios=0, count=12)
        self.assertIn("dormitorios", q.lower())

    def test_asks_budget_when_zone_and_bedrooms_known(self):
        q = _next_filter_question(zona="Oberá", presupuesto_max=0, dormitorios=1, count=12)
        self.assertIn("presupuesto", q.lower())

    def test_returns_none_when_all_filters_known(self):
        # Nothing left to narrow → caller shows the list instead of asking.
        self.assertIsNone(
            _next_filter_question(zona="Oberá", presupuesto_max=50000, dormitorios=1, count=12)
        )

    def test_threshold_constant_is_eight(self):
        # Locks the "show the list only when matches < 8" decision.
        self.assertEqual(_MAX_LIST, 8)


if __name__ == "__main__":
    unittest.main()
