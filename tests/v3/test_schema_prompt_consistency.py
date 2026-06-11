"""Plan #20: resolve select_property schema/prompt drift; drop echo/get_time.

- echo/get_time are no longer offered to the model (removed from _TOOL_NAMES and the
  prompt tool list) — they have no real-estate purpose and only invited off-task calls.
- select_property was in the action enum but never defined in the prompt taxonomy nor
  handled by the engine (dead) — removed from the enum.
- Every action in the schema enum must appear in the prompt taxonomy (consistency).

Offline — no LLM.
"""

import unittest

from app.routers.v3 import prompts
from app.routers.v3.schema import TURN_JSON_SCHEMA, _TOOL_NAMES


def _action_enum():
    return TURN_JSON_SCHEMA["schema"]["properties"]["action"]["enum"]


class TestSchemaPromptConsistency(unittest.TestCase):

    def test_echo_and_get_time_dropped_from_tools(self):
        self.assertNotIn("echo", _TOOL_NAMES)
        self.assertNotIn("get_time", _TOOL_NAMES)

    def test_echo_and_get_time_absent_from_prompt(self):
        p = prompts.build_system_prompt()
        self.assertNotIn("- echo:", p)
        self.assertNotIn("- get_time:", p)

    def test_select_property_removed_from_action_enum(self):
        self.assertNotIn("select_property", _action_enum())

    def test_real_tools_still_present(self):
        for name in ("search_properties", "schedule_visit", "get_faq_answer",
                     "cancel_appointment", "request_human_assistance"):
            self.assertIn(name, _TOOL_NAMES)

    def test_every_action_appears_in_prompt_taxonomy(self):
        p = prompts.build_system_prompt()
        for action in _action_enum():
            self.assertIn(action, p, f"action '{action}' missing from prompt taxonomy")


if __name__ == "__main__":
    unittest.main()
