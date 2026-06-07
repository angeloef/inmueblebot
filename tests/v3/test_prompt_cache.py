"""Phase 6 — Prompt-caching hygiene tests.

OpenAI caches the longest *static prefix* of the message list automatically. For
that to hit on every turn, the V3 path must keep the system prompt + tenant policy
byte-identical across turns and let only the tail (user message + state JSON) vary.

These tests assert that invariant structurally (no LLM needed):
  - build_system_prompt() is byte-stable (same object) across calls,
  - the system prompt carries no per-turn / per-tenant data,
  - build_messages() places the dynamic [ESTADO] block LAST,
  - across two turns the cached prefix (system + tenant policy) is identical and
    only the trailing messages differ.

Orchestrator runs these; do not execute manually.
"""

import asyncio
import unittest

from app.routers.v3 import prompts


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSystemPromptStable(unittest.TestCase):
    def test_byte_identical_across_calls(self):
        a = prompts.build_system_prompt()
        b = prompts.build_system_prompt()
        self.assertEqual(a, b)
        self.assertIs(a, b, "system prompt must be the same object (module constant)")

    def test_no_per_turn_or_tenant_data(self):
        p = prompts.build_system_prompt()
        # No dynamic state block, tenant id, or timestamp leaks into the cached block.
        self.assertNotIn("[ESTADO]", p)
        self.assertNotIn("[POLÍTICA DEL TENANT", p)
        self.assertNotIn("[POLITICA DEL TENANT", p)

    def test_negative_rule_ratio_under_cap(self):
        """R4 / playbook §4.6: keep hard negatives ≤ ~1:10 of non-empty lines."""
        import re
        p = prompts.build_system_prompt()
        lines = [ln for ln in p.splitlines() if ln.strip()]
        negatives = re.findall(r"\b(?:NUNCA|Nunca|nunca|CRÍTIC[OA]S?|ÚNICAMENTE)\b", p)
        # at most one hard-negative directive per 10 non-empty lines
        self.assertLessEqual(len(negatives), len(lines) / 10.0,
                             f"too many hard negatives: {len(negatives)} over {len(lines)} lines")


class TestTenantPolicyStable(unittest.TestCase):
    def test_same_tenant_same_policy(self):
        from uuid import uuid4
        tid = uuid4()
        self.assertEqual(_run(prompts.build_tenant_policy(tid)), _run(prompts.build_tenant_policy(tid)))

    def test_default_tenant_stable(self):
        self.assertEqual(_run(prompts.build_tenant_policy(None)), _run(prompts.build_tenant_policy(None)))

    def test_policy_has_tenant_block_header(self):
        pol = _run(prompts.build_tenant_policy(None))
        self.assertIn("[POLÍTICA DEL TENANT", pol)
        self.assertIn("Horario de atención", pol)


class TestMessageOrdering(unittest.TestCase):
    def _build(self, state_json, user_message, history=None):
        return prompts.build_messages(
            prompts.build_system_prompt(),
            _run(prompts.build_tenant_policy(None)),
            history or [],
            state_json,
            user_message,
        )

    def test_state_block_is_last(self):
        msgs = self._build('{"turno": 3}', "hola")
        self.assertEqual(msgs[-1]["role"], "system")
        self.assertTrue(msgs[-1]["content"].startswith("[ESTADO]"))

    def test_first_two_are_static_prefix(self):
        msgs = self._build('{"turno": 1}', "hola")
        self.assertEqual(msgs[0]["content"], prompts.build_system_prompt())
        self.assertEqual(msgs[1]["content"], _run(prompts.build_tenant_policy(None)))

    def test_cached_prefix_identical_across_turns_only_tail_varies(self):
        turn1 = self._build('{"turno": 1}', "busco depto", history=[])
        turn2 = self._build('{"turno": 2, "criterios": {"operation": "alquiler"}}',
                            "en el centro", history=["busco depto"])
        # The static prefix (system + tenant policy) must be byte-identical.
        self.assertEqual(turn1[0], turn2[0])
        self.assertEqual(turn1[1], turn2[1])
        # The dynamic tails differ.
        self.assertNotEqual(turn1[-1], turn2[-1])

    def test_no_state_block_when_empty(self):
        msgs = self._build("", "hola")
        self.assertFalse(any(m["content"].startswith("[ESTADO]") for m in msgs))


if __name__ == "__main__":
    unittest.main()
