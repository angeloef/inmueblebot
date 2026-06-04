"""Anti-hallucination structural guard tests.

Verifies that _assemble_response NEVER emits a confirmation when booking_succeeded
is False, even if the engine's response_plan contains confirmation text.

Orchestrator runs these; do not execute manually during Phase 4 implementation.
"""

import asyncio
import sys
import unittest

# ---------------------------------------------------------------------------
# Minimal stubs so tests import without DB/Redis/LLM connections
# ---------------------------------------------------------------------------

class _StubBelief:
    selected_property_id = 42
    search_criteria = {}
    active_intents = set()
    scheduling_day = "viernes"
    scheduling_time = "15:00"
    scheduling_name = "Juan"

class _StubResponsePlanItem:
    def __init__(self, type_, content):
        self.type = type_
        self.content = content

class _StubTurn:
    def __init__(self, action, response_plan):
        self.action = action
        self.response_plan = response_plan
        self.intent = "scheduling"
        self.missing_slot = None
        self.tool_calls = []
        self.confidence = 0.9
        self.selected_property_id = None
        self.belief_delta = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSchedulingGuardNoFakeConfirmation(unittest.TestCase):
    """_assemble_response must not let a fake confirmation reach the user."""

    def _call_assemble(self, turn, belief, booking_succeeded: bool, fsm_plan=None):
        from app.routers.v3.engine import _assemble_response
        return _run(
            _assemble_response(
                turn,
                belief,
                tool_results=[],
                any_ran=False,
                tenant_id=None,
                booking_succeeded=booking_succeeded,
                fsm_plan=fsm_plan,
            )
        )

    def test_book_step_no_success_discards_confirmation_plan(self):
        """When action==book_step and booking_succeeded==False, no Cita Agendada text."""
        confirmation_plan = [
            _StubResponsePlanItem("text", "📅 *¡Cita Agendada!* Tu visita está confirmada para el viernes."),
        ]
        turn = _StubTurn(action="book_step", response_plan=confirmation_plan)
        belief = _StubBelief()

        text, rich = self._call_assemble(turn, belief, booking_succeeded=False)

        self.assertNotIn("Cita Agendada", text, "Fake confirmation text leaked!")
        self.assertNotIn("CONFIRMED", text, "CONFIRMED marker leaked!")
        self.assertNotIn("confirmada", text.lower(), "Fake 'confirmada' leaked!")

    def test_book_step_with_success_allows_confirmation(self):
        """When booking_succeeded==True, a real confirmation is allowed through."""
        real_confirmation = [
            _StubResponsePlanItem(
                "text",
                "📅 *¡Cita Agendada!* Tu visita quedó confirmada para el viernes 15:00.\n\n<!--CONFIRMED:2026-06-06 15:00-->"
            ),
        ]
        turn = _StubTurn(action="book_step", response_plan=real_confirmation)
        belief = _StubBelief()

        text, rich = self._call_assemble(turn, belief, booking_succeeded=True)

        # Should contain confirmation text
        self.assertIn("Cita Agendada", text)
        # Marker must be stripped before reaching user
        self.assertNotIn("<!--CONFIRMED:", text, "Marker was not stripped!")

    def test_non_book_step_passes_through_normally(self):
        """action != book_step is unaffected by the guard."""
        info_plan = [
            _StubResponsePlanItem("text", "El departamento tiene 2 dormitorios."),
        ]
        turn = _StubTurn(action="clarify", response_plan=info_plan)
        belief = _StubBelief()

        text, rich = self._call_assemble(turn, belief, booking_succeeded=False)

        self.assertIn("departamento", text)

    def test_fsm_plan_overrides_engine_plan(self):
        """FSM override (fsm_plan provided) takes priority over engine response_plan."""
        engine_fake = [
            _StubResponsePlanItem("text", "📅 *¡Cita Agendada!*"),
        ]
        fsm_ask = [{"type": "text", "content": "¿Qué horario te viene bien?"}]
        turn = _StubTurn(action="book_step", response_plan=engine_fake)
        belief = _StubBelief()

        text, rich = self._call_assemble(
            turn, belief, booking_succeeded=False, fsm_plan=fsm_ask
        )

        self.assertIn("horario", text.lower())
        self.assertNotIn("Cita Agendada", text)

    def test_marker_stripped_from_tool_result_in_plain_text(self):
        """_strip_markers removes <!--CONFIRMED:…--> from any text."""
        from app.routers.v3.engine import _strip_markers

        raw = "Tu cita está lista.\n\n<!--CONFIRMED:2026-06-06 15:00-->"
        cleaned = _strip_markers(raw)
        self.assertNotIn("<!--CONFIRMED:", cleaned)
        self.assertIn("Tu cita", cleaned)

    def test_marker_not_in_text_unchanged(self):
        """_strip_markers is a no-op when no marker present."""
        from app.routers.v3.engine import _strip_markers

        raw = "El departamento tiene 2 dormitorios."
        self.assertEqual(raw, _strip_markers(raw))


if __name__ == "__main__":
    unittest.main()
