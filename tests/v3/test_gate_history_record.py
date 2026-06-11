"""Plan #24: safety-gate turns (emergency/human/OOS) are recorded in history.

Emergency / human-handoff / out-of-scope gates return BEFORE the normal
step-6/8c history bookkeeping, so the next engine turn never saw them — after an
out-of-scope joke the bot would re-greet as if the conversation just started.
`_record_gate_history` appends both sides and persists. These tests assert the
append + save + window-trim + fully-defensive behavior, plus the OOS gate wiring
end-to-end through run_turn.

All offline — Redis/save is stubbed; no real I/O.
"""

import asyncio
import unittest
from unittest.mock import patch, AsyncMock

from loguru import logger

from app.routers.v3 import engine as engine_mod
from app.routers.v3.belief import BeliefStateV5


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _LogCapture:
    """Capture loguru WARNING+ messages into a list for assertions."""

    def __enter__(self):
        self.messages: list[str] = []
        self._sink_id = logger.add(lambda m: self.messages.append(str(m)), level="WARNING")
        return self

    def __exit__(self, *exc):
        logger.remove(self._sink_id)
        return False


class TestRecordGateHistory(unittest.TestCase):

    def test_appends_both_sides_and_saves(self):
        belief = BeliefStateV5(session_id="s1")
        saved: list = []
        with patch("app.routers.v3.belief.save_belief_v5",
                   new=AsyncMock(side_effect=lambda b: saved.append(b))):
            _run(engine_mod._record_gate_history(belief, "contame un chiste", "No puedo ayudarte con eso."))
        self.assertEqual(belief.history[-2], "user: contame un chiste")
        self.assertEqual(belief.history[-1], "assistant: No puedo ayudarte con eso.")
        self.assertEqual(len(saved), 1)
        self.assertIs(saved[0], belief)

    def test_window_trim(self):
        # Pre-fill beyond HISTORY_WINDOW so the append forces a trim.
        from app.core.config import get_settings
        window = get_settings().HISTORY_WINDOW
        belief = BeliefStateV5(session_id="s2")
        belief.history = [f"user: old {i}" for i in range(window + 5)]
        with patch("app.routers.v3.belief.save_belief_v5", new=AsyncMock()):
            _run(engine_mod._record_gate_history(belief, "hola", "respuesta"))
        self.assertEqual(len(belief.history), window)
        # Newest entries survive the trim.
        self.assertEqual(belief.history[-1], "assistant: respuesta")
        self.assertEqual(belief.history[-2], "user: hola")

    def test_defensive_on_save_failure(self):
        belief = BeliefStateV5(session_id="s3")
        with patch("app.routers.v3.belief.save_belief_v5",
                   new=AsyncMock(side_effect=RuntimeError("redis down"))), \
             _LogCapture() as cap:
            # Must not raise.
            _run(engine_mod._record_gate_history(belief, "hola", "respuesta"))
        self.assertTrue(any("Failed to record gate turn" in m for m in cap.messages), cap.messages)


class TestOutOfScopeGateRecordsHistory(unittest.TestCase):
    """End-to-end: an OOS message flows through run_turn and the turn is recorded."""

    def test_oos_turn_recorded_via_run_turn(self):
        belief = BeliefStateV5(session_id="s4")
        saved: list = []
        joke = "contame un chiste de futbol"
        # Sanity: this message is genuinely classified out-of-scope.
        self.assertTrue(engine_mod._is_out_of_scope(joke))
        with patch("app.routers.v3.belief.load_belief_v5", new=AsyncMock(return_value=belief)), \
             patch("app.routers.v3.belief.save_belief_v5",
                   new=AsyncMock(side_effect=lambda b: saved.append(list(b.history)))):
            result = _run(engine_mod.run_turn(phone="s4", user_message=joke, tenant_id=None))
        # The gate response reached the user...
        self.assertEqual(result["response_text"], engine_mod._OUT_OF_SCOPE_RESPONSE)
        # ...and the turn was persisted so the next engine call can see it.
        self.assertEqual(len(saved), 1)
        self.assertIn(f"user: {joke}", saved[0])
        self.assertIn(f"assistant: {engine_mod._OUT_OF_SCOPE_RESPONSE}", saved[0])


if __name__ == "__main__":
    unittest.main()
