"""Regression tests for the greeting→scheduling contamination bug.

Bug history (2026-06-02): the greeting "buenas tardes" matched the bare word
"tarde" in TIME_PATTERN, which seeded belief.scheduling_time and flipped on the
"scheduling" intent. On the next (search) turn, the directive engine injected
"ACCIÓN: Falta el día. Preguntá solo por el día." into the specialist prompt,
overriding the user's real search request — the bot replied "¿Qué día te
gustaría coordinar?" with tools=[] instead of searching.

Root cause was architectural: regex-extracted state could *create* an intent and
the directive engine emitted an imperative command that overrode the actual
message. Fix:
  1. Scheduling extraction in update_belief() only runs inside an active
     scheduling context (intent already set or awaiting=scheduling_*).
  2. build_context_prompt() no longer injects an imperative directive; state is
     surfaced as descriptive facts and the LLM specialist decides.
  3. TIME_PATTERN no longer matches bare "mañana/tarde/noche" (greetings/idioms).

Run: pytest tests/test_greeting_scheduling_regression.py -v
"""
import pytest

from app.core.belief_state import get_belief
from app.core.state_transitioner import update_belief, TIME_PATTERN
from app.core.context_aggregator import build_context_prompt


class TestGreetingDoesNotSeedScheduling:
    def test_greeting_then_search_has_no_scheduling_state(self):
        """The exact failing chatlog: greeting then a fresh property search."""
        b = get_belief("regr-greeting-search")
        update_belief(b, "hola buenas tardes?")
        update_belief(
            b,
            "estoy buscando un departamento para alquilar en obera, "
            "cerca de la unam, monoamiente o de 1 habitacion",
        )
        assert b.scheduling_time == "", "greeting must not seed scheduling_time"
        assert b.scheduling_day == "", "greeting must not seed scheduling_day"
        assert "scheduling" not in b.active_intents, (
            "a greeting/search must never create the scheduling intent"
        )
        # And the search intent IS present.
        assert "searching" in b.active_intents

    @pytest.mark.parametrize("greeting", [
        "hola buenas tardes?",
        "buenas noches, estás?",
        "buen día, una consulta",
    ])
    def test_various_greetings_do_not_create_scheduling(self, greeting):
        b = get_belief(f"regr-greet-{greeting[:6]}")
        update_belief(b, greeting)
        assert "scheduling" not in b.active_intents
        assert b.scheduling_time == ""


class TestNoImperativeDirective:
    def test_context_prompt_has_no_imperative_directive(self):
        """The prompt must surface facts, not an 'ACCIÓN: hacé X' command that
        can override the user's real message."""
        b = get_belief("regr-no-directive")
        update_belief(b, "hola buenas tardes?")
        update_belief(b, "busco depto en alquiler cerca de la unam, 1 ambiente")
        ctx = build_context_prompt(b)
        assert "DIRECTIVA" not in ctx
        assert "ACCIÓN" not in ctx
        # No phantom scheduling vocabulary leaking into a pure search turn.
        assert "coordinar" not in ctx.lower()


class TestSchedulingFlowStillWorks:
    def test_explicit_scheduling_captures_day_and_time(self):
        b = get_belief("regr-sched-explicit")
        b.selected_property_id = 7
        update_belief(b, "quiero agendar una visita el viernes a las 15")
        assert "scheduling" in b.active_intents
        assert b.scheduling_day  # "viernes"
        assert b.scheduling_time  # "a las 15"

    def test_awaiting_reply_captures_time_of_day(self):
        b = get_belief("regr-sched-awaiting")
        b.awaiting = "scheduling_time"
        update_belief(b, "a la tarde")
        assert b.scheduling_time  # captured inside the booking flow


class TestTimePatternPrecision:
    @pytest.mark.parametrize("text", [
        "buenas tardes",
        "buenas noches",
        "se hace tarde",
        "más tarde te escribo",
    ])
    def test_bare_temporal_words_no_longer_match(self, text):
        assert TIME_PATTERN.search(text) is None

    @pytest.mark.parametrize("text", [
        "a la tarde",
        "por la mañana",
        "3 de la tarde",
        "mediodía",
        "a las 15",
        "15:30",
    ])
    def test_real_time_expressions_still_match(self, text):
        assert TIME_PATTERN.search(text) is not None
