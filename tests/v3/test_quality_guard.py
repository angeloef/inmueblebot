"""Phase 6 — Quality guard (gated rubric judge) tests.

Covers the gating decision (pure, no LLM) and the run_guard orchestration with the
LLM calls stubbed, proving:
  - the common high-confidence non-critical turn skips the judge (no extra call),
  - low-confidence and critical turns are judged,
  - a judge FAIL triggers exactly one regeneration,
  - a judge PASS leaves the text untouched,
  - every failure path fails open (keeps the original text, never raises).

Orchestrator runs these; do not execute manually.
"""

import asyncio
import unittest

from app.routers.v3 import guard


class _Settings:
    V3_JUDGE_ENABLED = True
    V3_JUDGE_CONFIDENCE_THRESHOLD = 0.70
    V3_JUDGE_PASS_THRESHOLD = 0.60


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── should_judge (pure) ────────────────────────────────────────────────────────

class TestShouldJudge(unittest.TestCase):
    def setUp(self):
        self.s = _Settings()

    def test_high_confidence_non_critical_skips(self):
        self.assertFalse(guard.should_judge("search", 0.95, self.s))

    def test_low_confidence_triggers(self):
        self.assertTrue(guard.should_judge("search", 0.40, self.s))

    def test_critical_action_triggers_even_high_confidence(self):
        for action in ("book_step", "handoff", "answer_knowledge"):
            self.assertTrue(guard.should_judge(action, 0.99, self.s), action)

    def test_disabled_never_judges(self):
        self.s.V3_JUDGE_ENABLED = False
        self.assertFalse(guard.should_judge("book_step", 0.10, self.s))

    def test_threshold_boundary_exclusive(self):
        # confidence == threshold is NOT below threshold → only critical would fire
        self.assertFalse(guard.should_judge("search", 0.70, self.s))


# ── run_guard (LLM stubbed) ────────────────────────────────────────────────────

class TestRunGuard(unittest.TestCase):
    def setUp(self):
        self.s = _Settings()
        self._orig_judge = guard._judge
        self._orig_regen = guard._regenerate

    def tearDown(self):
        guard._judge = self._orig_judge
        guard._regenerate = self._orig_regen

    def _stub_judge(self, verdict):
        async def _j(*a, **k):
            return verdict
        guard._judge = _j

    def _stub_regen(self, text, recorder=None):
        async def _r(*a, **k):
            if recorder is not None:
                recorder.append(True)
            return text
        guard._regenerate = _r

    def _call(self, *, action, confidence, text="Hola, tengo 3 opciones para vos."):
        return _run(
            guard.run_guard(
                action=action,
                confidence=confidence,
                user_message="busco depto",
                response_text=text,
                state_json="{}",
                tool_results=[],
                settings=self.s,
            )
        )

    def test_skipped_turn_returns_original_no_score(self):
        called = []
        self._stub_judge(guard.JudgeVerdict(score=0.1, passed=False, issue="x"))
        # monkeypatch to detect it was NOT called by recording
        async def _j(*a, **k):
            called.append(True)
            return guard.JudgeVerdict(score=0.1, passed=False, issue="x")
        guard._judge = _j

        res = self._call(action="search", confidence=0.95)

        self.assertEqual(res.response_text, "Hola, tengo 3 opciones para vos.")
        self.assertIsNone(res.judge_score)
        self.assertFalse(res.regenerated)
        self.assertEqual(called, [], "judge should not run on a non-gated turn")

    def test_pass_keeps_original_with_score(self):
        self._stub_judge(guard.JudgeVerdict(score=0.9, passed=True, issue=None))
        regen_called = []
        self._stub_regen("REGENERATED", regen_called)

        res = self._call(action="book_step", confidence=0.9)

        self.assertEqual(res.response_text, "Hola, tengo 3 opciones para vos.")
        self.assertEqual(res.judge_score, 0.9)
        self.assertFalse(res.regenerated)
        self.assertEqual(regen_called, [], "no regen on a passing judge")

    def test_fail_triggers_single_regeneration(self):
        self._stub_judge(guard.JudgeVerdict(score=0.3, passed=False, issue="doble pregunta"))
        regen_called = []
        self._stub_regen("Respuesta corregida.", regen_called)

        res = self._call(action="search", confidence=0.4)

        self.assertEqual(res.response_text, "Respuesta corregida.")
        self.assertEqual(res.judge_score, 0.3)
        self.assertTrue(res.regenerated)
        self.assertEqual(len(regen_called), 1, "exactly one regeneration")

    def test_fail_then_regen_empty_keeps_original(self):
        self._stub_judge(guard.JudgeVerdict(score=0.3, passed=False, issue="loop"))
        self._stub_regen(None)  # regeneration yields nothing

        res = self._call(action="search", confidence=0.4)

        self.assertEqual(res.response_text, "Hola, tengo 3 opciones para vos.")
        self.assertEqual(res.judge_score, 0.3)
        self.assertFalse(res.regenerated)

    def test_judge_none_fails_open(self):
        async def _j(*a, **k):
            return None
        guard._judge = _j

        res = self._call(action="handoff", confidence=0.2)

        self.assertEqual(res.response_text, "Hola, tengo 3 opciones para vos.")
        self.assertIsNone(res.judge_score)
        self.assertFalse(res.regenerated)

    def test_empty_text_untouched(self):
        called = []
        async def _j(*a, **k):
            called.append(True)
            return guard.JudgeVerdict(score=0.1, passed=False, issue="x")
        guard._judge = _j

        res = self._call(action="show_photos", confidence=0.1, text="")

        self.assertEqual(res.response_text, "")
        self.assertEqual(called, [], "image-only/empty turns are not judged")


if __name__ == "__main__":
    unittest.main()
