"""Plan #42: search_properties `tipo` accepts multiple CSV values (e.g. "depto,casa").

Pure unit tests for the parsing/labeling helpers -- no DB. The `.in_()` query
swap itself is exercised indirectly: these helpers are the only place the
plural fallback strings and the WHERE-clause value list are built, so if they
behave correctly for 0/1/2+ types the query behavior follows.
"""

import unittest

from app.tools.v2.search_properties import (
    _describe_filters,
    _parse_tipos,
    _tipo_plural_label,
)


class TestParseTipos(unittest.TestCase):
    def test_empty_returns_empty_list(self):
        self.assertEqual(_parse_tipos(""), [])

    def test_single_type_backward_compat(self):
        self.assertEqual(_parse_tipos("departamento"), ["departamento"])

    def test_maps_synonyms_to_canonical(self):
        self.assertEqual(_parse_tipos("depto"), ["departamento"])
        self.assertEqual(_parse_tipos("casas"), ["casa"])

    def test_csv_multiple_types(self):
        self.assertEqual(_parse_tipos("departamento,casa"), ["departamento", "casa"])

    def test_csv_with_spaces_and_synonyms(self):
        self.assertEqual(_parse_tipos("depto, casas"), ["departamento", "casa"])

    def test_dedupes_preserving_order(self):
        self.assertEqual(_parse_tipos("casa,casa,depto"), ["casa", "departamento"])

    def test_unrecognized_term_passes_through_lowercased(self):
        self.assertEqual(_parse_tipos("Loft"), ["loft"])

    def test_empty_terms_discarded(self):
        self.assertEqual(_parse_tipos("casa,,depto"), ["casa", "departamento"])


class TestTipoPluralLabel(unittest.TestCase):
    def test_no_types_gives_propiedades(self):
        self.assertEqual(_tipo_plural_label([]), "propiedades")

    def test_single_type(self):
        self.assertEqual(_tipo_plural_label(["casa"]), "casas")

    def test_ph_is_invariant(self):
        self.assertEqual(_tipo_plural_label(["ph"]), "ph")

    def test_two_types_joined_with_y(self):
        self.assertEqual(
            _tipo_plural_label(["departamento", "casa"]), "departamentos y casas"
        )


class TestDescribeFiltersMultiTipo(unittest.TestCase):
    def test_single_tipo_unchanged(self):
        # Retrocompat: existing behavior for one type must not change.
        desc = _describe_filters("alquiler", "casa", "Centro", 0, 1)
        self.assertIn("casas", desc)

    def test_csv_tipo_describes_both(self):
        desc = _describe_filters("alquiler", "departamento,casa", "Centro", 0, 0)
        self.assertIn("departamentos y casas", desc)


if __name__ == "__main__":
    unittest.main()
