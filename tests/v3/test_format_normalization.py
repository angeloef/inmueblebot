"""Plan #19: curated FAQ prices use dot-thousands; no-results msg keeps accents.

The curated 'precios' fallback used comma-thousands ($40,000) which violates the
Argentine dot-thousands rule the rest of the bot follows, and the search no-results
message dropped accents ("No encontre… Queres… algun"). These assert the corrected
forms.

Offline — no LLM / DB.
"""

import re
import unittest

from app.tools.v2.get_faq_answer import _fallback_faq


class TestFaqPriceFormat(unittest.TestCase):

    def test_precios_has_no_comma_thousands(self):
        text = _fallback_faq("precios")
        self.assertIsNotNone(text)
        # No "$40,000" style anywhere.
        self.assertIsNone(re.search(r"\$\d{1,3},\d{3}", text), text)

    def test_precios_uses_dot_thousands(self):
        text = _fallback_faq("precios")
        self.assertIn("$40.000", text)
        self.assertIn("$5.500.000", text)
        self.assertIn("$22.000.000", text)


class TestNoResultsAccents(unittest.TestCase):

    def test_no_results_message_has_accents(self):
        import app.tools.v2.search_properties as sp
        src = __import__("inspect").getsource(sp)
        # The corrected literal is present and the un-accented one is gone.
        self.assertIn("No encontré propiedades", src)
        self.assertIn("¿Querés ajustar algún filtro?", src)
        self.assertNotIn("No encontre propiedades", src)
        self.assertNotIn("Queres ajustar algun filtro", src)


if __name__ == "__main__":
    unittest.main()
