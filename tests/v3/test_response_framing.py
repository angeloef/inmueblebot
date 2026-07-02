"""Plan #44: native framing emitted by the engine's own structured call.

Supersedes plan #43's LLM-wrap mechanism. `turn.framing` (intro/outro, both
nullable) rides in the SAME call that already produces tool_calls/response_plan —
zero extra LLM calls. The non-negotiable guarantee carries over unchanged: the
hard-data block (ID:N — Tipo en Zona — $Precio + specs) reaches the user
byte-for-byte, with framing present, absent, invalid, or with the flag off.

All offline — no network / DB / Redis.
"""

import unittest
from unittest.mock import patch

from app.routers.v3.engine import _apply_framing, _apply_framing_intro_only
from app.routers.v3.schema import Framing


_VERBATIM = (
    "Encontré 2 propiedades:\n"
    "  ID:12 — Departamento en Centro — $35.976/mes\n"
    "     2 dorm | 1 baño | 60 m²\n"
    "  ID:7 — Casa en Schuster — $85.000.000\n"
    "     3 dorm | 2 baños | 120 m²"
)


class _StubTurn:
    def __init__(self, intro=None, outro=None):
        self.framing = Framing(intro=intro, outro=outro)


def _settings(enabled=True):
    return type("S", (), {"RESPONSE_FRAMING_ENABLED": enabled})()


class TestApplyFraming(unittest.TestCase):

    def test_both_null_returns_block_byte_identical(self):
        turn = _StubTurn(intro=None, outro=None)
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertEqual(out, _VERBATIM)

    def test_intro_and_outro_wrap_the_block(self):
        turn = _StubTurn(intro="¡Buenísimo! Mirá lo que encontré:", outro="¿Querés ver fotos de alguna?")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertIn(_VERBATIM, out)
        self.assertIn("¡Buenísimo!", out)
        self.assertIn("¿Querés ver fotos", out)
        # Prices untouched — no drift.
        self.assertIn("$35.976/mes", out)
        self.assertIn("$85.000.000", out)

    def test_intro_leaking_a_price_is_dropped(self):
        turn = _StubTurn(intro="Este depto sale $999.999!", outro="¿Te copa?")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertNotIn("$999.999", out)
        self.assertIn("¿Te copa?", out)
        self.assertIn(_VERBATIM, out)

    def test_outro_leaking_a_property_id_is_dropped(self):
        turn = _StubTurn(intro="Mirá esto:", outro="El ID:99 es buenísimo")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertNotIn("ID:99", out)
        self.assertIn("Mirá esto:", out)
        self.assertIn(_VERBATIM, out)

    def test_natural_language_price_leak_without_dollar_sign_is_dropped(self):
        # Security-review finding: a literal "$"/"id:" substring check misses
        # spelled-out numeric leaks. Any digit anywhere is treated as unsafe.
        turn = _StubTurn(intro="Te la alquilan a 35.976 pesos por mes", outro="¿Te copa?")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertNotIn("35.976 pesos", out)
        self.assertIn("¿Te copa?", out)
        self.assertIn(_VERBATIM, out)

    def test_natural_language_id_leak_without_id_prefix_is_dropped(self):
        turn = _StubTurn(intro="Mirá esto:", outro="La propiedad 7 es buenísima")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertNotIn("propiedad 7", out)
        self.assertIn("Mirá esto:", out)
        self.assertIn(_VERBATIM, out)

    def test_overlong_framing_is_dropped(self):
        turn = _StubTurn(intro="x" * 500, outro=None)
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertEqual(out, _VERBATIM)

    def test_flag_off_returns_block_untouched_even_with_framing(self):
        turn = _StubTurn(intro="¡Hola!", outro="Chau")
        with patch("app.core.config.get_settings", return_value=_settings(enabled=False)):
            out = _apply_framing(turn, _VERBATIM)
        self.assertEqual(out, _VERBATIM)

    def test_missing_framing_attribute_is_treated_as_null(self):
        turn = type("T", (), {})()  # no .framing at all (e.g. legacy stub in other tests)
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertEqual(out, _VERBATIM)

    def test_outro_dropped_when_verbatim_already_ends_in_a_question(self):
        # plan #46: progressive narrowing / no-results blocks already end in "?" —
        # an outro would stack a second question in the same message, breaking
        # "una sola pregunta por mensaje" even if the LLM ignores the prompt rule.
        verbatim = "Encontré 21 propiedades en alquiler. ¿En qué zona buscás?"
        turn = _StubTurn(intro="¡Buenísimo!", outro="¿Querés que te muestre fotos?")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, verbatim)
        self.assertIn(verbatim, out)
        self.assertIn("¡Buenísimo!", out)
        self.assertNotIn("¿Querés que te muestre fotos?", out)
        self.assertEqual(out.count("?"), 1)

    def test_outro_kept_when_verbatim_does_not_end_in_a_question(self):
        turn = _StubTurn(intro=None, outro="¿Querés ver fotos de alguna?")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing(turn, _VERBATIM)
        self.assertIn("¿Querés ver fotos", out)


class TestApplyFramingIntroOnly(unittest.TestCase):

    CONFIRMATION = "¡Listo! Tu visita quedó agendada para el jueves 16hs en Av. Siempre Viva 742."

    def test_intro_is_prepended(self):
        turn = _StubTurn(intro="¡Genial, ya casi lo tenemos!", outro="esto se ignora")
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing_intro_only(turn, self.CONFIRMATION)
        self.assertTrue(out.startswith("¡Genial, ya casi lo tenemos!"))
        self.assertIn(self.CONFIRMATION, out)
        # outro is never applied on booking confirmations — LOCKED decision.
        self.assertNotIn("esto se ignora", out)

    def test_null_intro_returns_confirmation_untouched(self):
        turn = _StubTurn(intro=None, outro=None)
        with patch("app.core.config.get_settings", return_value=_settings()):
            out = _apply_framing_intro_only(turn, self.CONFIRMATION)
        self.assertEqual(out, self.CONFIRMATION)

    def test_flag_off_returns_confirmation_untouched(self):
        turn = _StubTurn(intro="¡Hola!", outro=None)
        with patch("app.core.config.get_settings", return_value=_settings(enabled=False)):
            out = _apply_framing_intro_only(turn, self.CONFIRMATION)
        self.assertEqual(out, self.CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
