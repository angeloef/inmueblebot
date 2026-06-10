"""Plan #9: multi-intent turns concatenate verbatim block + synthesized remainder.

"busco depto en el centro, ¿y qué requisitos piden?" makes the engine run BOTH
search_properties (verbatim list) and get_faq_answer (requisitos). The old Path 0b2
returned only the first verbatim hit and dropped the FAQ answer. Now the verbatim
block is followed by a synthesized tail from the remaining data tools.

All offline — _synthesize_from_results is stubbed; no LLM / DB / Redis.
"""

import asyncio
import unittest
from unittest.mock import patch


class _StubBelief:
    selected_property_id = None
    search_criteria = {}
    active_intents = set()
    last_search_context = ""


class _StubToolCall:
    def __init__(self, name):
        self.name = name


class _StubTurn:
    def __init__(self, action, tools):
        self.action = action
        self.tool_calls = [_StubToolCall(n) for n in tools]
        self.response_plan = []
        self.intent = "search"
        self.missing_slot = None
        self.confidence = 0.9
        self.selected_property_id = None
        self.belief_delta = None


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _assemble(turn, belief, tools_used, tool_results, user_message="", synth_return="TAIL"):
    from app.routers.v3 import engine

    async def _fake_synth(_belief, results, _user_message=""):
        return synth_return

    with patch.object(engine, "_synthesize_from_results", _fake_synth):
        return _run(engine._assemble_response(
            turn, belief,
            tool_results=tool_results,
            any_ran=True,
            tenant_id=None,
            booking_succeeded=False,
            tools_used=tools_used,
            user_message=user_message,
        ))


class TestMultiToolConcat(unittest.TestCase):

    def test_search_plus_faq_concatenates_both(self):
        turn = _StubTurn("search", ["search_properties", "get_faq_answer"])
        text, _rich = _assemble(
            turn, _StubBelief(),
            tools_used=["search_properties", "get_faq_answer"],
            tool_results=["Departamento ID:7 en Centro $200.000", "Requisitos: garantía propietaria."],
            user_message="busco depto en el centro, ¿y qué requisitos piden?",
            synth_return="Piden garantía propietaria y recibo de sueldo.",
        )
        self.assertIn("ID:7 en Centro", text)  # verbatim list survives
        self.assertIn("garantía propietaria", text)  # FAQ tail appended

    def test_search_only_returns_verbatim_no_tail(self):
        turn = _StubTurn("search", ["search_properties"])
        text, _rich = _assemble(
            turn, _StubBelief(),
            tools_used=["search_properties"],
            tool_results=["Departamento ID:7 en Centro $200.000"],
            synth_return="SHOULD_NOT_APPEAR",
        )
        self.assertIn("ID:7 en Centro", text)
        self.assertNotIn("SHOULD_NOT_APPEAR", text)

    def test_detail_wins_over_list_for_verbatim_block(self):
        turn = _StubTurn("show_details", ["search_properties", "get_property_details"])
        text, _rich = _assemble(
            turn, _StubBelief(),
            tools_used=["search_properties", "get_property_details"],
            tool_results=["LIST: ID:7, ID:8", "DETALLE ID:7 — 2 amb, $200.000"],
            synth_return="",
        )
        self.assertIn("DETALLE ID:7", text)

    def test_faq_error_remainder_is_skipped(self):
        """An errored second tool must not be synthesized into the tail."""
        turn = _StubTurn("search", ["search_properties", "get_faq_answer"])
        text, _rich = _assemble(
            turn, _StubBelief(),
            tools_used=["search_properties", "get_faq_answer"],
            tool_results=["Departamento ID:7 en Centro", "Error: faq lookup failed"],
            synth_return="SHOULD_NOT_APPEAR",
        )
        self.assertIn("ID:7 en Centro", text)
        self.assertNotIn("SHOULD_NOT_APPEAR", text)


if __name__ == "__main__":
    unittest.main()
