"""Regression tests for the errors found in test chat #3 (the "buenas noches" booking
conversation). Offline only — pure belief/routing/prompt logic, no LLM calls.

Errors covered:
  E1  booking failed at the final step with empty slots + leaked internal message
  E2  rapport prompt told the bot to say the forbidden "te derivo al especialista"
  E4  details dropped in the details+photos turn
  E5  asked for a phone / misrouted visit intent
  E6  "todos los que tengas" did not run a search
  E2.3 service question should check the property first, then FAQ

Run: pytest tests/test_chat3_fixes_regression.py -v
"""
import asyncio
import inspect

import pytest

from app.core.belief_state import get_belief
from app.core.state_transitioner import update_belief
import app.routers.router as router
import app.routers.v2_adapter as v2_adapter
from app.agents.coordinator import SPECIALISTS
from app.agents.s2_agent import process_message_with_specialist


class TestE1SchedulingSlotCapture:
    """Once scheduling is active, the spontaneous day+time+name message must populate
    the belief slots so the booking step has its data."""

    def test_slots_captured_when_scheduling_active(self):
        b = get_belief("e1-capture")
        b.selected_property_id = 2
        b.active_intents.add("scheduling")  # established by the visit-intent fast-path
        update_belief(
            b,
            "me queda bien el viernes a la tarde, mi nombre es angelo y mi numero "
            "es por el que te estoy hablando",
        )
        assert b.scheduling_day, "day must be captured"
        assert b.scheduling_time, "time must be captured"
        assert b.scheduling_name, "name must be captured"


class TestE1bNoInternalLeak:
    """schedule_visit's missing-data message must be user-facing, never developer wording."""

    def test_missing_message_is_user_facing(self):
        from app.tools.v2.schedule_visit import schedule_visit
        msg = asyncio.run(schedule_visit(property_id=0, nombre="", dia=""))
        low = msg.lower()
        assert "schedule_visit" not in low
        assert "especialista" not in low
        assert "recolectar" not in low


class TestE5VisitIntentRouting:
    """Visit-intent phrases must be detectable so they route to scheduling, not search."""

    @pytest.mark.parametrize("text", [
        "quiero verlo en persona",
        "me gustaría visitarlo",
        "quiero coordinar una visita",
        "quiero ir a verlo",
    ])
    def test_visit_intent_detected(self, text):
        assert bool(router._VISIT_PHRASE.search(text) or router._SCHEDULING_VERB.search(text))


class TestE2RapportNoDerivation:
    """The rapport prompt must not instruct the bot to announce a handoff/derivation."""

    def test_prompt_forbids_derivation_language(self):
        prompt = SPECIALISTS["rapport"].system_prompt.lower()
        # The old buggy instruction was: "indicá que lo vas a derivar al especialista"
        assert "vas a derivar" not in prompt
        assert "te derivo al especialista" not in prompt
        # And it should explicitly forbid the phrase.
        assert "prohibido" in prompt or "nunca digas" in prompt


class TestE23KnowledgeChecksProperty:
    """Knowledge specialist must be able to inspect the property before answering FAQ."""

    def test_knowledge_has_property_details_tool(self):
        assert "get_property_details" in SPECIALISTS["knowledge"].tool_names
        assert "get_faq_answer" in SPECIALISTS["knowledge"].tool_names


class TestE4DetailsHelper:
    def test_resolve_details_helper_exists(self):
        assert hasattr(v2_adapter, "_resolve_details_for_belief")


class TestE6ForceToolSupported:
    def test_specialist_accepts_force_tool(self):
        sig = inspect.signature(process_message_with_specialist)
        assert "force_tool" in sig.parameters
