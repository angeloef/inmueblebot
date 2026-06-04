"""Offline tests for the eval-harness core (no DB/Redis/LLM).

Covers the deterministic surface: case loading/validation, code+rule graders, the
pass@k / pass^k math, and turn_passed semantics. The model grader and the adapter
runner need a live runtime and are exercised by `tests/eval/run_eval.py`, not here.
"""

import pytest

from tests.eval.graders import GraderResult, grade_code, grade_rule, turn_passed
from tests.eval.metrics import CaseResult, CaseRun, aggregate
from tests.eval.schema import Case, Expectation, load_cases


# ── case loading ─────────────────────────────────────────────────────────────

def test_starter_cases_load_and_are_valid():
    cases = load_cases()
    assert len(cases) >= 10
    assert all(c.id and c.turns for c in cases)
    # both splits present
    splits = {c.split for c in cases}
    assert splits == {"dev", "holdout"}
    # ids unique (load_cases raises on dup, but assert anyway)
    assert len({c.id for c in cases}) == len(cases)


def test_holdout_and_dev_are_disjoint_ids():
    dev = {c.id for c in load_cases("dev")}
    holdout = {c.id for c in load_cases("holdout")}
    assert dev and holdout
    assert dev.isdisjoint(holdout)


def test_invalid_split_rejected():
    with pytest.raises(ValueError):
        Case.from_dict({"id": "x", "split": "bogus", "turns": [{"user": "hi"}]})


# ── code grader ──────────────────────────────────────────────────────────────

def test_code_grader_tools_any():
    exp = Expectation(tools_any=["search_properties"])
    assert grade_code(exp, ["search_properties"], {}).passed
    assert not grade_code(exp, ["get_time"], {}).passed


def test_code_grader_tools_none_and_booking():
    exp = Expectation(tools_none=["schedule_visit"], booking=False)
    assert grade_code(exp, ["search_properties"], {}).passed
    bad = grade_code(exp, ["schedule_visit"], {})
    assert not bad.passed
    # both the forbidden-tool and booking assertions should fire
    assert len(bad.reasons) == 2


def test_code_grader_selection():
    exp = Expectation(selection=True)
    assert grade_code(exp, [], {"selected_property_id": 7}).passed
    assert not grade_code(exp, [], {}).passed


# ── rule grader ──────────────────────────────────────────────────────────────

def test_rule_grader_regex_none_blocks_fake_confirmation():
    exp = Expectation(regex_none=[r"visita (confirmada|agendada)"])
    assert not grade_rule(exp, "Listo, tu visita confirmada para el jueves").passed
    assert grade_rule(exp, "¿Para qué día querés coordinar?").passed


def test_rule_grader_nonempty_and_maxlen():
    assert not grade_rule(Expectation(nonempty=True), "   ").passed
    assert not grade_rule(Expectation(max_len=5), "demasiado largo").passed


# ── turn_passed semantics ────────────────────────────────────────────────────

def test_human_flag_does_not_fail_turn():
    results = [
        GraderResult(passed=True, grader="code"),
        GraderResult(passed=True, grader="human", human_flag=True),
    ]
    assert turn_passed(results)
    results.append(GraderResult(passed=False, grader="rule"))
    assert not turn_passed(results)


# ── metrics math ─────────────────────────────────────────────────────────────

def _case(case_id, run_passes):
    runs = [CaseRun(passed=p, latency_ms_total=100.0, cost_usd_total=0.001, human_flags=0)
            for p in run_passes]
    return CaseResult(case_id, "holdout", [], runs)


def test_pass_at_k_and_pow_k():
    # case A: 2/3 pass → counts for pass@k (capability) but not pass^k (consistency)
    # case B: 3/3 pass → counts for both
    # case C: 0/3 pass → neither
    results = [
        _case("A", [True, False, True]),
        _case("B", [True, True, True]),
        _case("C", [False, False, False]),
    ]
    summary = aggregate(results, k=3)
    assert summary["cases"] == 3
    # aggregate() rounds to 4 decimals → compare with abs tolerance accordingly
    assert summary["pass@3"] == pytest.approx(2 / 3, abs=1e-3)   # A, B reachable
    assert summary["pass^3"] == pytest.approx(1 / 3, abs=1e-3)   # only B consistent
    # pass@1 = mean of per-case run-pass fractions = (2/3 + 1 + 0)/3
    assert summary["pass@1"] == pytest.approx((2 / 3 + 1.0 + 0.0) / 3, abs=1e-3)
    assert summary["failing_cases"] == ["A", "C"]


def test_latency_and_cost_aggregation():
    results = [_case("A", [True, True])]
    summary = aggregate(results, k=2)
    assert summary["latency_ms_mean"] == pytest.approx(100.0)
    assert summary["cost_usd_total"] == pytest.approx(0.002)
