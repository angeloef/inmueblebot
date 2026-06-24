"""KA4 offline tests — lead scoring + tool wiring (no DB / network).

Covers the deterministic parts: the score_lead heuristic, the registry
registration of the two new tools, arg validation, and the V4-only schema enum
extension (V3 must stay untouched).
"""

from app.tools.v2 import leads
from app.tools.v2.registry import TOOL_REGISTRY, validate_tool_args
from app.routers.v4.schema import _V4_TOOL_NAMES
from app.routers.v3.schema import _TOOL_NAMES


# ── score_lead ────────────────────────────────────────────────────────────────

def test_score_lead_hot_when_full_signal_and_high_urgency():
    score, tier = leads.score_lead(150000, "Centro", "alta", "departamento")
    assert score == 1.0
    assert tier == "hot"


def test_score_lead_cold_when_no_signal():
    score, tier = leads.score_lead(0, "", "", "")
    assert score == 0.0
    assert tier == "cold"


def test_score_lead_warm_band():
    # budget (0.3) + zona (0.2) = 0.5 → warm
    score, tier = leads.score_lead(120000, "Belgrano", "", "")
    assert score == 0.5
    assert tier == "warm"


def test_score_lead_free_text_urgency_counts_as_high():
    # "esta semana" is treated as high urgency.
    score, _ = leads.score_lead(0, "", "esta semana", "")
    assert score == 0.3


# ── registry wiring ───────────────────────────────────────────────────────────

def test_lead_tools_registered():
    for name in ("capture_lead", "qualify_lead"):
        assert name in TOOL_REGISTRY
        func, is_async, schema = TOOL_REGISTRY[name]
        assert is_async is True
        assert schema["function"]["name"] == name


def test_lead_tools_have_no_required_args():
    # Both tools must tolerate partial info — every field optional.
    for name in ("capture_lead", "qualify_lead"):
        ok, err = validate_tool_args(name, {})
        assert ok, err


# ── schema enum: V4 extends, V3 stays clean ──────────────────────────────────

def test_v4_enum_includes_lead_tools():
    assert "capture_lead" in _V4_TOOL_NAMES
    assert "qualify_lead" in _V4_TOOL_NAMES


def test_v3_enum_not_polluted_by_lead_tools():
    assert "capture_lead" not in _TOOL_NAMES
    assert "qualify_lead" not in _TOOL_NAMES
