"""Tests for the too-broad search narrowing feature.

When search_properties returns more than _NARROW_RESULT_THRESHOLD (9) results and one
or more search criteria are still missing, the bot asks for UP TO TWO criteria before
showing the list. The user can answer one or both at once.

Run: pytest tests/test_search_narrowing.py -v
"""
from app.core.belief_state import get_belief
from app.routers.router import (
    _maybe_narrow_search,
    _next_narrow_criterion,
    _capture_narrow_field,
    _SHOW_ALL_ANYWAY,
    _NARROW_RESULT_THRESHOLD,
    _NARROW_FIELD_HINT,
)


def _belief_with(ids, **criteria):
    b = get_belief(f"narrow-{id(criteria)}-{len(list(ids))}")
    b.last_search_ids = list(ids)
    # reset criteria to a clean slate, then apply
    b.operation = None
    b.property_type = None
    b.zone = None
    b.bedrooms_min = None
    b.budget_max = None
    for k, v in criteria.items():
        setattr(b, k, v)
    return b


class TestNarrowThreshold:
    def test_few_results_no_narrowing(self):
        b = _belief_with(range(1, 6), operation="alquiler")  # 5 results
        assert _maybe_narrow_search(b) is None

    def test_exactly_threshold_no_narrowing(self):
        b = _belief_with(range(1, _NARROW_RESULT_THRESHOLD + 1))  # 9 results
        assert _maybe_narrow_search(b) is None

    def test_above_threshold_asks(self):
        b = _belief_with(range(1, 13))  # 12 results, nothing set
        out = _maybe_narrow_search(b)
        assert out is not None
        text, fields_key = out
        assert "12 opciones" in text
        # Primary (first) field is always "operation" when nothing is set
        assert fields_key.split(",")[0] == "operation"

    def test_two_criteria_asked_when_two_missing(self):
        """When op+type are set but zone+bedrooms are missing, both asked at once."""
        b = _belief_with(range(1, 15), operation="alquiler", property_type="departamento")
        out = _maybe_narrow_search(b)
        assert out is not None
        text, fields_key = out
        primary, secondary = fields_key.split(",")
        assert primary == "zone"
        assert secondary == "bedrooms_min"
        # Message should contain the primary question AND the secondary hint
        assert "zona" in text.lower()
        assert "dormitorios" in text.lower()
        assert "También" in text or "también" in text

    def test_single_criterion_when_one_remaining(self):
        """When only one criterion is still missing, ask only for that one (no 'también')."""
        b = _belief_with(
            range(1, 15),
            operation="alquiler", property_type="departamento",
            zone="Centro", bedrooms_min=1,
            # budget_max is the only missing one
        )
        out = _maybe_narrow_search(b)
        assert out is not None
        text, fields_key = out
        assert "," not in fields_key   # single field, no comma
        assert fields_key == "budget_max"


class TestCriterionOrder:
    def test_asks_operation_first_when_all_missing(self):
        b = _belief_with(range(1, 13))
        assert _next_narrow_criterion(b)[0] == "operation"

    def test_asks_zone_when_op_and_type_set(self):
        """Primary field is zone; secondary hint about dormitorios included."""
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento")
        text, fields_key = _maybe_narrow_search(b)
        # Primary field is zone
        assert fields_key.split(",")[0] == "zone"
        assert "zona" in text.lower()

    def test_asks_bedrooms_then_budget(self):
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento", zone="Centro")
        assert _next_narrow_criterion(b)[0] == "bedrooms_min"
        b.bedrooms_min = 2
        assert _next_narrow_criterion(b)[0] == "budget_max"


class TestTerminates:
    def test_all_criteria_filled_shows_list(self):
        b = _belief_with(
            range(1, 20),  # 19 results
            operation="alquiler", property_type="departamento",
            zone="Centro", bedrooms_min=2, budget_max=120000,
        )
        assert _next_narrow_criterion(b) is None
        assert _maybe_narrow_search(b) is None

    def test_iteration_reduces_when_criteria_added(self):
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento")
        assert _next_narrow_criterion(b)[0] == "zone"
        b.zone = "Centro"
        assert _next_narrow_criterion(b)[0] == "bedrooms_min"
        b.bedrooms_min = 1
        assert _next_narrow_criterion(b)[0] == "budget_max"
        b.budget_max = 90000
        assert _next_narrow_criterion(b) is None


class TestCaptureNarrowField:
    """The awaiting handler must capture bare answers the generic extractors skip."""

    def test_capture_bare_bedrooms(self):
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento", zone="Centro")
        assert _capture_narrow_field(b, "bedrooms_min", "2") is True
        assert b.bedrooms_min == 2

    def test_capture_budget_phrase(self):
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento",
                         zone="Centro", bedrooms_min=1)
        assert _capture_narrow_field(b, "budget_max", "hasta 90 mil") is True
        assert b.budget_max and b.budget_max > 0

    def test_capture_operation(self):
        b = _belief_with(range(1, 13))
        assert _capture_narrow_field(b, "operation", "para alquilar") is True
        assert b.operation == "alquiler"

    def test_capture_returns_false_on_garbage(self):
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento", zone="Centro")
        # no number present → cannot set bedrooms
        assert _capture_narrow_field(b, "bedrooms_min", "no sé bien") is False

    def test_capture_both_fields_from_combined_response(self):
        """When user answers both zone AND dormitorios at once, both are captured."""
        import app.core.state_transitioner as st
        b = _belief_with(range(1, 15), operation="alquiler", property_type="departamento")
        # Simulate update_belief already having run (zone captured by generic extractor)
        st.update_belief(b, "en el centro, 1 dormitorio")
        # Now simulate the handler looping over both fields
        _capture_narrow_field(b, "zone", "en el centro, 1 dormitorio")
        _capture_narrow_field(b, "bedrooms_min", "en el centro, 1 dormitorio")
        assert b.zone == "Centro"
        assert b.bedrooms_min == 1

    def test_capture_only_one_when_user_answers_partial(self):
        """User answers only zone (not dormitorios) — zone set, bedrooms stays None."""
        import app.core.state_transitioner as st
        b = _belief_with(range(1, 15), operation="alquiler", property_type="departamento")
        st.update_belief(b, "en el centro")
        _capture_narrow_field(b, "zone", "en el centro")
        _capture_narrow_field(b, "bedrooms_min", "en el centro")
        assert b.zone == "Centro"
        assert b.bedrooms_min is None   # user didn't specify, stays missing


class TestCriteriaAny:
    """When user explicitly says 'don't care about X', narrowing must skip that criterion."""

    def test_zone_any_skipped_in_narrowing(self):
        """After 'cualquier zona', zone must not appear in the narrowing question."""
        import app.core.state_transitioner as st
        b = _belief_with(range(1, 15), operation="alquiler", property_type="departamento")
        # Simulate "cualquier zona"
        st.update_belief(b, "puede ser cualquier zona mientras sea en obera")
        assert "zone" in b.criteria_any, "criteria_any must contain 'zone' after broadening"
        assert b.zone is None

        out = _maybe_narrow_search(b)
        assert out is not None
        text, fields_key = out
        # Zone must NOT be asked
        assert "zone" not in fields_key.split(","), f"zone should be skipped, got {fields_key}"
        # Bedrooms should be next
        assert fields_key.split(",")[0] == "bedrooms_min"

    def test_explicit_zone_clears_criteria_any(self):
        """After user says 'cualquier zona' and then provides a specific zone,
        criteria_any is cleared and zone is used in filtering."""
        import app.core.state_transitioner as st
        b = _belief_with(range(1, 15), operation="alquiler", property_type="departamento")
        st.update_belief(b, "puede ser cualquier zona")
        assert "zone" in b.criteria_any
        # Now user provides a specific zone
        st.update_belief(b, "mejor en el centro")
        assert b.zone == "Centro"
        assert "zone" not in b.criteria_any, "criteria_any must clear when explicit zone given"

    def test_type_switch_does_not_add_zone_to_criteria_any(self):
        """A type switch resets zone but does NOT add it to criteria_any
        (user may still want to specify a zone for the new type)."""
        import app.core.state_transitioner as st
        b = _belief_with(range(1, 15), operation="alquiler", property_type="departamento",
                         zone="Centro")
        st.update_belief(b, "y alguna casa?")
        assert b.zone is None             # zone reset by type switch
        assert "zone" not in b.criteria_any  # NOT marked as explicit any

        # So narrowing WILL ask for zone again
        out = _maybe_narrow_search(b)
        assert out is not None
        fields_key = out[1]
        assert "zone" in fields_key.split(","), "zone should be asked after type switch"

    def test_chat_log_scenario(self):
        """Reproduce the exact failing scenario from the chat log:
        'para alquilar, cualquier zona' → narrowing should ask dormitorios, NOT zona."""
        import app.core.state_transitioner as st
        b = _belief_with(range(1, 22))  # 21 results, nothing set
        st.update_belief(b, "busco un departamento en obera")
        # Simulate first narrowing: 21 results → bot asks op + type/zone hint
        # (awaiting = search_narrow:operation,property_type — handled elsewhere)
        # Simulate user answering both op and "cualquier zona":
        st.update_belief(b, "para alquilar, puede ser cualquier zona mientras sea en obera")
        assert b.operation == "alquiler"
        assert "zone" in b.criteria_any
        assert b.zone is None

        # After re-search: 14 results, zone in criteria_any → only ask dormitorios
        b.last_search_ids = list(range(1, 15))  # 14 results
        out = _maybe_narrow_search(b)
        assert out is not None
        text, fields_key = out
        primary = fields_key.split(",")[0]
        assert primary == "bedrooms_min", (
            f"Expected 'bedrooms_min' as first question, got '{primary}'. "
            "Bot should NOT ask for zone again after user said 'cualquier zona'."
        )
        assert "zona" not in text.lower() or "dormitorio" in text.lower()


class TestShowAllEscape:
    def test_show_all_patterns(self):
        for msg in ["mostrame todos igual", "no importa, mostrame todo", "me da igual", "ver todas"]:
            assert _SHOW_ALL_ANYWAY.search(msg) is not None

    def test_normal_answer_not_show_all(self):
        assert _SHOW_ALL_ANYWAY.search("centro") is None
