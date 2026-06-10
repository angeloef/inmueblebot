"""Plan #2: requested-but-none-ran → targeted clarify, never the placeholder.

When the engine requests tools but ALL are skipped by validation (e.g. a
property-scoped tool with no property_id and no selection), _assemble_response
must ask a question that moves the conversation forward instead of rendering the
engine's dead-end placeholder ("Un momento, reviso eso.").

All offline — no LLM / DB / Redis.
"""

import asyncio
import unittest


class _StubBelief:
    selected_property_id = None
    search_criteria = {}
    active_intents = set()


class _StubResponsePlanItem:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content


class _StubToolCall:
    def __init__(self, name):
        self.name = name


class _StubTurn:
    def __init__(self, action, tool_calls, response_plan=None):
        self.action = action
        self.tool_calls = tool_calls
        self.response_plan = response_plan or [
            _StubResponsePlanItem("text", "Un momento, reviso eso."),
        ]
        self.intent = "search"
        self.missing_slot = None
        self.confidence = 0.5
        self.selected_property_id = None
        self.belief_delta = None


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _assemble(turn, belief):
    from app.routers.v3.engine import _assemble_response
    return _run(_assemble_response(
        turn, belief,
        tool_results=[],
        any_ran=False,
        tenant_id=None,
        booking_succeeded=False,
        tools_used=[],
    ))


class TestSkippedToolClarify(unittest.TestCase):

    def test_show_photos_no_selection_asks_which_property(self):
        turn = _StubTurn("show_photos", [_StubToolCall("get_property_images")])
        text, _rich = _assemble(turn, _StubBelief())
        self.assertIn("De cuál propiedad", text)
        self.assertNotIn("Un momento", text)

    def test_show_details_no_selection_asks_which_property(self):
        turn = _StubTurn("show_details", [_StubToolCall("get_property_details")])
        text, _rich = _assemble(turn, _StubBelief())
        self.assertIn("De cuál propiedad", text)
        self.assertNotIn("Un momento", text)

    def test_non_property_skip_falls_back_to_safe_clarify_not_placeholder(self):
        turn = _StubTurn("answer_knowledge", [_StubToolCall("get_faq_answer")])
        text, _rich = _assemble(turn, _StubBelief())
        self.assertNotIn("Un momento", text)
        self.assertNotIn("De cuál propiedad", text)
        self.assertIn("Disculpá", text)

    def test_with_selection_does_not_ask_which_property(self):
        """If a property IS selected, the targeted property question must not fire."""
        belief = _StubBelief()
        belief.selected_property_id = 7
        turn = _StubTurn("show_photos", [_StubToolCall("get_property_images")])
        text, _rich = _assemble(turn, belief)
        self.assertNotIn("De cuál propiedad", text)

    def test_no_tools_requested_does_not_trigger(self):
        """No tool_calls at all → this path must not fire (engine plan renders)."""
        turn = _StubTurn("smalltalk", [], response_plan=[
            _StubResponsePlanItem("text", "¡Hola! ¿En qué te ayudo?"),
        ])
        text, _rich = _assemble(turn, _StubBelief())
        self.assertIn("Hola", text)


if __name__ == "__main__":
    unittest.main()
