"""Plan #7: ground _synthesize_from_results in the user question + history tail.

LLM Call 2 used to receive only the tool dump + compact state, so it could answer
a different question than the user asked (a generic FAQ instead of the pet-policy
that was asked). These tests assert the synthesis prompt now carries the user's
actual question and the recent conversation, and that the history-tail helper drops
the trailing current-user message.

All offline — the LLM client is stubbed; no network / DB / Redis.
"""

import asyncio
import unittest
from unittest.mock import patch


class _StubBelief:
    def __init__(self, history=None):
        self.search_criteria = {}
        self.selected_property_id = None
        self.last_search_context = ""
        self.awaiting = None
        self.last_action = None
        self.last_intent = None
        self.scheduling_day = ""
        self.scheduling_time = ""
        self.scheduling_name = ""
        self.active_intents = set()
        self.turn_count = 1
        self.history = history or []


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _Capture:
    """Captures the messages passed to the stubbed LLM create() call."""

    def __init__(self):
        self.messages = None

    def install(self):
        capture = self

        class _Completions:
            async def create(self, *, model, messages, **kwargs):
                capture.messages = messages
                return _FakeResponse('{"response": "ok"}')

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

        return _Client()


def _synth(belief, tool_results, user_message):
    """Run _synthesize_from_results with the LLM + parser stubbed; return captured msgs."""
    from app.routers.v3 import engine
    capture = _Capture()
    fake_client = capture.install()
    with patch("app.agents.cs_llm_client.get_client", return_value=fake_client), \
         patch("app.agents.cs_llm_client.get_model", return_value="stub"), \
         patch("app.agents.cs_llm_client.max_tokens_kwarg", return_value={}), \
         patch("app.core.response_parser.get_final_response_format", return_value=None), \
         patch("app.core.response_parser.parse_llm_response", return_value=("ok", {})):
        _run(engine._synthesize_from_results(belief, tool_results, user_message))
    return capture.messages


def _user_content(messages):
    return next(m["content"] for m in messages if m["role"] == "user")


class TestRecentHistoryTail(unittest.TestCase):

    def test_drops_trailing_current_user_message(self):
        from app.routers.v3.engine import _recent_history_tail
        belief = _StubBelief(history=[
            "user: hola",
            "assistant: ¡Hola! ¿Qué buscás?",
            "user: ¿aceptan mascotas?",  # current message, must be dropped
        ])
        tail = _recent_history_tail(belief)
        self.assertIn("assistant: ¡Hola! ¿Qué buscás?", tail)
        self.assertNotIn("¿aceptan mascotas?", tail)

    def test_returns_empty_for_no_history(self):
        from app.routers.v3.engine import _recent_history_tail
        self.assertEqual(_recent_history_tail(_StubBelief()), "")

    def test_caps_to_max_entries(self):
        from app.routers.v3.engine import _recent_history_tail
        history = [f"user: m{i}" for i in range(10)]
        tail = _recent_history_tail(belief=_StubBelief(history=history), max_entries=4)
        # last entry is "user: m9" (current) → dropped; then last 4 of the remaining 9
        self.assertEqual(len(tail.splitlines()), 4)
        self.assertIn("m8", tail)
        self.assertNotIn("m4", tail)


class TestSynthesisGrounding(unittest.TestCase):

    def test_user_question_is_in_the_prompt(self):
        belief = _StubBelief(history=["user: ¿aceptan mascotas?"])
        messages = _synth(belief, ["[1] Sí, se aceptan mascotas."], "¿aceptan mascotas?")
        content = _user_content(messages)
        self.assertIn("Pregunta del usuario:", content)
        self.assertIn("¿aceptan mascotas?", content)

    def test_history_tail_is_in_the_prompt(self):
        belief = _StubBelief(history=[
            "user: busco depto en el centro",
            "assistant: Encontré 3 departamentos en Centro.",
            "user: ¿cuál es el más barato?",  # current
        ])
        messages = _synth(belief, ["[1] ID:12 $200.000"], "¿cuál es el más barato?")
        content = _user_content(messages)
        self.assertIn("Conversación reciente:", content)
        self.assertIn("Encontré 3 departamentos en Centro.", content)

    def test_tool_results_still_present(self):
        belief = _StubBelief()
        messages = _synth(belief, ["[1] ID:7 Casa en venta"], "mostrame casas")
        content = _user_content(messages)
        self.assertIn("Resultados de herramientas:", content)
        self.assertIn("ID:7 Casa en venta", content)

    def test_no_question_uses_generic_instruction(self):
        belief = _StubBelief()
        messages = _synth(belief, ["[1] dato"], "")
        content = _user_content(messages)
        self.assertNotIn("Pregunta del usuario:", content)
        self.assertIn("Respondé al usuario basándote en estos resultados.", content)


if __name__ == "__main__":
    unittest.main()
