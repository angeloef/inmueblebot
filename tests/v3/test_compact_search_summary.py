"""Plan #21: last_search_context stores compact per-ID lines, not a 1200-char blob.

A char-truncated blob could cut an entry mid-line, so descriptive selection ("la de
Schuster") might reference a half-line. The compact summary keeps whole ID header
lines (id + tipo + zona + precio), drops spec/footer noise, and caps the count.

Offline — exercises _compact_search_summary directly.
"""

import unittest

from app.routers.v3.engine import _compact_search_summary, _MAX_SUMMARY_LINES


_FORMATTED = """Encontré 2 propiedades:
  ID:12 — Departamento en Centro — $250.000/mes
     2 dorm | 1 baño | 60 m²
  ID:7 — Casa en Schuster — $85.000.000
     3 dorm | 2 baños | 120 m²
¿Querés ver los detalles de alguna?"""


class TestCompactSearchSummary(unittest.TestCase):

    def test_keeps_only_id_header_lines(self):
        out = _compact_search_summary(_FORMATTED)
        self.assertIn("ID:12 — Departamento en Centro — $250.000/mes", out)
        self.assertIn("ID:7 — Casa en Schuster — $85.000.000", out)

    def test_drops_spec_and_prose_lines(self):
        out = _compact_search_summary(_FORMATTED)
        self.assertNotIn("dorm |", out)
        self.assertNotIn("Encontré 2 propiedades", out)
        self.assertNotIn("¿Querés ver los detalles", out)

    def test_one_line_per_property(self):
        out = _compact_search_summary(_FORMATTED)
        self.assertEqual(len(out.splitlines()), 2)

    def test_caps_line_count(self):
        many = "\n".join(f"  ID:{i} — Departamento en Centro — $100.000/mes" for i in range(30))
        out = _compact_search_summary(many)
        self.assertEqual(len(out.splitlines()), _MAX_SUMMARY_LINES)

    def test_never_truncates_an_entry(self):
        out = _compact_search_summary(_FORMATTED)
        for line in out.splitlines():
            self.assertTrue(line.startswith("ID:"))
            self.assertIn("$", line)  # price intact, not cut mid-line

    def test_fallback_for_non_list_message(self):
        msg = "No encontré propiedades con esos filtros. ¿Querés ajustar algún filtro?"
        out = _compact_search_summary(msg)
        self.assertEqual(out, msg)  # falls back to the (short) prose verbatim


if __name__ == "__main__":
    unittest.main()
