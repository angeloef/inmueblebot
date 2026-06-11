"""Plan #25: bedroom range (bedrooms_max + bedrooms_match) survives refinement.

"2 a 3 dormitorios" used to live only in the search_properties tool args, so a
later refinement ("y en el centro?") re-built the search from belief criteria and
silently reverted to exact/min — dropping the range. These tests assert the new
fields are carried through BeliefDelta → apply_belief_delta → serialize round-trip
→ the `criterios` context block, and that the match-mode vocabulary matches the
tool (`exact` | `at_least` | `range`).

All offline — no Redis, no LLM, no DB.
"""

import unittest

from app.routers.v3.schema import BeliefDelta, TURN_JSON_SCHEMA
from app.routers.v3.belief import (
    BeliefStateV5,
    apply_belief_delta,
    serialize_v5,
    deserialize_v5,
    migrate_v4_to_v5,
)
from app.routers.v3.engine import _compact_state
from app.core.belief_state import ConversationBeliefState


class TestSchema(unittest.TestCase):

    def test_belief_delta_accepts_range_fields(self):
        d = BeliefDelta(bedrooms_min=2, bedrooms_max=3, bedrooms_match="range")
        self.assertEqual(d.bedrooms_max, 3)
        self.assertEqual(d.bedrooms_match, "range")

    def test_json_schema_lists_new_fields_as_required(self):
        props = TURN_JSON_SCHEMA["schema"]["properties"]["belief_delta"]
        self.assertIn("bedrooms_max", props["properties"])
        self.assertIn("bedrooms_match", props["properties"])
        # strict mode → every property must be in required
        self.assertIn("bedrooms_max", props["required"])
        self.assertIn("bedrooms_match", props["required"])

    def test_match_enum_matches_tool_vocabulary(self):
        enum = TURN_JSON_SCHEMA["schema"]["properties"]["belief_delta"][
            "properties"]["bedrooms_match"]["enum"]
        self.assertEqual(set(enum), {"exact", "at_least", "range", None})


class TestApplyDelta(unittest.TestCase):

    def test_applies_range_fields(self):
        belief = BeliefStateV5(session_id="s1")
        belief = apply_belief_delta(
            belief, BeliefDelta(bedrooms_min=2, bedrooms_max=3, bedrooms_match="range"))
        self.assertEqual(belief.bedrooms_max, 3)
        self.assertEqual(belief.bedrooms_match, "range")

    def test_null_never_clears_stored_range(self):
        belief = BeliefStateV5(session_id="s2", bedrooms_min=2, bedrooms_max=3,
                               bedrooms_match="range")
        # A later turn mentions only a zone → range fields null in delta.
        belief = apply_belief_delta(belief, BeliefDelta(zone="Centro"))
        self.assertEqual(belief.zone, "Centro")
        self.assertEqual(belief.bedrooms_max, 3)        # preserved
        self.assertEqual(belief.bedrooms_match, "range")  # preserved


class TestPersistence(unittest.TestCase):

    def test_serialize_roundtrip_preserves_range(self):
        belief = BeliefStateV5(session_id="s3", bedrooms_min=2, bedrooms_max=3,
                               bedrooms_match="range")
        restored = deserialize_v5(serialize_v5(belief), "s3")
        self.assertEqual(restored.bedrooms_max, 3)
        self.assertEqual(restored.bedrooms_match, "range")

    def test_migrate_v4_defaults_to_none(self):
        v4 = ConversationBeliefState(session_id="s4", bedrooms_min=2)
        v5 = migrate_v4_to_v5(v4, "s4")
        self.assertIsNone(v5.bedrooms_max)
        self.assertIsNone(v5.bedrooms_match)

    def test_deserialize_legacy_v4_blob_has_none_range(self):
        # A blob with no range keys (old data) must not blow up.
        legacy = '{"session_id": "s5", "bedrooms_min": 2, "schema_version": 5}'
        restored = deserialize_v5(legacy, "s5")
        self.assertIsNone(restored.bedrooms_max)
        self.assertIsNone(restored.bedrooms_match)


class TestCriteriosState(unittest.TestCase):

    def test_compact_state_surfaces_range(self):
        belief = BeliefStateV5(session_id="s6", operation="alquiler",
                               property_type="departamento", bedrooms_min=2,
                               bedrooms_max=3, bedrooms_match="range")
        state = _compact_state(belief)
        criterios = state["criterios"]
        self.assertEqual(criterios["dormitorios_mín"], 2)
        self.assertEqual(criterios["dormitorios_máx"], 3)
        self.assertEqual(criterios["dormitorios_modo"], "range")

    def test_compact_state_omits_range_when_absent(self):
        belief = BeliefStateV5(session_id="s7", operation="alquiler",
                               property_type="departamento", bedrooms_min=2)
        criterios = _compact_state(belief)["criterios"]
        self.assertNotIn("dormitorios_máx", criterios)
        self.assertNotIn("dormitorios_modo", criterios)


if __name__ == "__main__":
    unittest.main()
