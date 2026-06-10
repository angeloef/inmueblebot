"""Plan #8: gate the Step 7b RAG safety-net for answer-about-shown-results.

When the user asks a comparative/price question about the JUST-SHOWN search list
("¿cuál es la más barata?"), the model labels it intent==search but may pick
answer_knowledge with no tool. The RAG safety-net must NOT fire in that case —
injecting FAQ/property chunks drowns the answer that lives in ultima_busqueda.

These cover the gating predicate _is_about_shown_results directly (offline).
"""

import unittest


class _Turn:
    def __init__(self, intent, action="answer_knowledge"):
        self.intent = intent
        self.action = action


class _Belief:
    def __init__(self, last_search_context=""):
        self.last_search_context = last_search_context


class TestRagSafetyNetGate(unittest.TestCase):

    def test_search_intent_with_results_skips_net(self):
        from app.routers.v3.engine import _is_about_shown_results
        turn = _Turn(intent="search")
        belief = _Belief(last_search_context="ID:12 Centro $200.000")
        self.assertTrue(_is_about_shown_results(turn, belief))

    def test_search_intent_without_results_runs_net(self):
        from app.routers.v3.engine import _is_about_shown_results
        turn = _Turn(intent="search")
        belief = _Belief(last_search_context="")
        self.assertFalse(_is_about_shown_results(turn, belief))

    def test_knowledge_intent_runs_net_even_with_results(self):
        """A real FAQ question (intent=knowledge) must still hit the net."""
        from app.routers.v3.engine import _is_about_shown_results
        turn = _Turn(intent="knowledge")
        belief = _Belief(last_search_context="ID:12 Centro $200.000")
        self.assertFalse(_is_about_shown_results(turn, belief))

    def test_missing_intent_attr_is_safe(self):
        from app.routers.v3.engine import _is_about_shown_results

        class _NoIntent:
            action = "answer_knowledge"

        belief = _Belief(last_search_context="ID:12")
        self.assertFalse(_is_about_shown_results(_NoIntent(), belief))


if __name__ == "__main__":
    unittest.main()
