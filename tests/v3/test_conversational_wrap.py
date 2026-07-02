"""Plan #43: conversational intro/outro wrap around a byte-identical verbatim block.

The non-negotiable guarantee: whatever the LLM returns as framing, the hard-data
block (ID:N — Tipo en Zona — $Precio + specs) reaches the user byte-for-byte. The
LLM never regenerates it — the code concatenates it between a generated intro/outro.

All offline — the OpenAI client is stubbed; no network / DB / Redis.
"""

import asyncio
import unittest
from unittest.mock import patch, AsyncMock

import app.agents.cs_llm_client  # noqa: F401 -- force-import before get_settings is patched below
from app.routers.v3.engine import _wrap_verbatim_with_intro_outro, _WRAP_DEFAULT_INTRO


_VERBATIM = (
    "Encontré 2 propiedades:\n"
    "  ID:12 — Departamento en Centro — $35.976/mes\n"
    "     2 dorm | 1 baño | 60 m²\n"
    "  ID:7 — Casa en Schuster — $85.000.000\n"
    "     3 dorm | 2 baños | 120 m²"
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_client(content):
    """AsyncOpenAI-shaped stub whose chat.completions.create returns `content`."""
    msg = type("M", (), {"content": content})
    choice = type("C", (), {"message": msg})
    resp = type("R", (), {"choices": [choice]})
    client = type("Client", (), {})()
    client.chat = type("Chat", (), {})()
    client.chat.completions = type("Comp", (), {})()
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


class TestConversationalWrap(unittest.TestCase):

    def _wrap(self, flag, client=None, raises=False):
        settings = type("S", (), {"CONVERSATIONAL_WRAP_ENABLED": flag})()
        with patch("app.core.config.get_settings", return_value=settings):
            if client is None and not raises:
                return _run(_wrap_verbatim_with_intro_outro("busco depto en el centro", _VERBATIM))
            with patch("app.agents.cs_llm_client.get_client", return_value=client), \
                 patch("app.agents.cs_llm_client.get_model", return_value="gpt-5.4-mini"):
                return _run(_wrap_verbatim_with_intro_outro("busco depto en el centro", _VERBATIM))

    def test_flag_off_returns_block_untouched(self):
        # Prod-safe default: exact current behavior, byte-identical, no LLM call.
        out = self._wrap(flag=False)
        self.assertEqual(out, _VERBATIM)

    def test_block_is_byte_identical_when_wrapped(self):
        client = _fake_client('{"intro": "¡Buenísimo! Mirá lo que encontré:", "outro": "¿Querés ver fotos de alguna?"}')
        out = self._wrap(flag=True, client=client)
        # Non-negotiable: the full block survives byte-for-byte as a substring.
        self.assertIn(_VERBATIM, out)
        self.assertIn("¡Buenísimo!", out)
        self.assertIn("¿Querés ver fotos", out)
        # Prices untouched — no drift.
        self.assertIn("$35.976/mes", out)
        self.assertIn("$85.000.000", out)

    def test_llm_failure_falls_back_to_default_intro_plus_block(self):
        client = _fake_client(None)
        client.chat.completions.create = AsyncMock(side_effect=RuntimeError("timeout"))
        out = self._wrap(flag=True, client=client)
        self.assertTrue(out.startswith(_WRAP_DEFAULT_INTRO))
        self.assertIn(_VERBATIM, out)  # block still delivered, byte-identical

    def test_empty_llm_output_falls_back_to_default(self):
        client = _fake_client('{"intro": "", "outro": ""}')
        out = self._wrap(flag=True, client=client)
        self.assertTrue(out.startswith(_WRAP_DEFAULT_INTRO))
        self.assertIn(_VERBATIM, out)

    def test_intro_leaking_a_price_is_rejected(self):
        # Defense-in-depth: if the LLM ignores the "never mention prices" instruction
        # (e.g. via prompt injection through user_message), drop that text rather than
        # risk a hallucinated/stale price reaching the user outside the verbatim block.
        client = _fake_client('{"intro": "Este depto sale $999.999!", "outro": "¿Te copa?"}')
        out = self._wrap(flag=True, client=client)
        self.assertNotIn("$999.999", out)
        self.assertIn("¿Te copa?", out)
        self.assertIn(_VERBATIM, out)

    def test_outro_leaking_a_property_id_is_rejected(self):
        client = _fake_client('{"intro": "Mirá esto:", "outro": "El ID:99 es buenísimo"}')
        out = self._wrap(flag=True, client=client)
        self.assertNotIn("ID:99", out)
        self.assertIn("Mirá esto:", out)
        self.assertIn(_VERBATIM, out)


if __name__ == "__main__":
    unittest.main()
