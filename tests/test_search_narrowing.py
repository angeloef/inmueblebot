"""Tests for the too-broad search narrowing feature.

When search_properties returns more than _NARROW_RESULT_THRESHOLD (9) results and a
search criterion is still missing, the bot asks for ONE more criterion before showing
the list, iterating turn-by-turn until the list is small enough OR all criteria are set.

Run: pytest tests/test_search_narrowing.py -v
"""
from app.core.belief_state import get_belief
from app.routers.router import (
    _maybe_narrow_search,
    _next_narrow_criterion,
    _capture_narrow_field,
    _SHOW_ALL_ANYWAY,
    _NARROW_RESULT_THRESHOLD,
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
        text, field = out
        assert "12 opciones" in text
        assert field == "operation"


class TestCriterionOrder:
    def test_asks_operation_first_when_all_missing(self):
        b = _belief_with(range(1, 13))
        assert _next_narrow_criterion(b)[0] == "operation"

    def test_asks_zone_when_op_and_type_set(self):
        b = _belief_with(range(1, 13), operation="alquiler", property_type="departamento")
        text, field = _maybe_narrow_search(b)
        assert field == "zone"
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


class TestShowAllEscape:
    def test_show_all_patterns(self):
        for msg in ["mostrame todos igual", "no importa, mostrame todo", "me da igual", "ver todas"]:
            assert _SHOW_ALL_ANYWAY.search(msg) is not None

    def test_normal_answer_not_show_all(self):
        assert _SHOW_ALL_ANYWAY.search("centro") is None
