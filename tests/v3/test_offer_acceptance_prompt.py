"""Plan #12: offer-acceptance few-shot is present in the system prompt.

When a search fallback offered other options ("¿Querés que te las muestre?") and the
user says "sí, dale", the model must re-run search_properties minus the failed
filter instead of replying smalltalk and stranding the user. This is a prompt-only
fix (§3.3); the test locks the few-shot into the prompt and checks the R4 negative
ratio is still under cap with the added MALO line.

Offline — no LLM.
"""

import re
import unittest

from app.routers.v3 import prompts


class TestOfferAcceptancePrompt(unittest.TestCase):

    def test_few_shot_present(self):
        p = prompts.build_system_prompt()
        self.assertIn("Aceptación de una oferta del sistema", p)
        self.assertIn("sí, dale", p)
        self.assertIn("SIN el filtro que falló", p)

    def test_prompt_still_byte_stable(self):
        self.assertIs(prompts.build_system_prompt(), prompts.build_system_prompt())

    def test_negative_rule_ratio_under_cap(self):
        """Mirror of the R4 cap guard so the added MALO line can't silently breach it."""
        p = prompts.build_system_prompt()
        lines = [ln for ln in p.splitlines() if ln.strip()]
        negatives = [ln for ln in lines if re.match(r"\s*(MALO|NUNCA|NO\b)", ln)]
        self.assertLessEqual(len(negatives) / max(len(lines), 1), 0.10)


if __name__ == "__main__":
    unittest.main()
