"""Tests for V4 KA3 — evidence evaluator + abstention.

All offline (no DB, no LLM calls). Tests the scoring logic and abstention
decision. Minimal fixtures — the evaluator is a pure function.
"""

from __future__ import annotations

import pytest
from app.routers.v4.evidence_eval import (
    evaluate_evidence_pool,
    ABSTAIN_THRESHOLD,
    EvidenceEvaluation,
    ABSTAIN_RESPONSE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pool(evidence_items: list[dict]) -> list[dict]:
    return [{"intent": "knowledge", "args_hint": "{}", "evidence": evidence_items}]


def _rag_item(source: str = "rag_faq", id: str = "1", text: str = "x" * 60) -> dict:
    return {"source": source, "id": id, "text": text, "score": 0.8, "timestamp": "2026-06-24"}


def _memory_item(source: str = "episodic", text: str = "y" * 60) -> dict:
    return {"source": source, "id": "sess1", "text": text, "score": 1.0, "timestamp": ""}


# ── Abstention cases ──────────────────────────────────────────────────────────

def test_empty_pool_abstains_on_knowledge_action():
    eval_ = evaluate_evidence_pool([], action="answer_knowledge")
    assert eval_.should_abstain is True
    assert eval_.abstain_reason == "no_evidence"
    assert eval_.confidence < ABSTAIN_THRESHOLD


def test_no_pool_abstains_on_answer_faq():
    eval_ = evaluate_evidence_pool([], action="answer_faq")
    assert eval_.should_abstain is True


def test_only_memory_items_abstains_on_knowledge_action():
    """Memory items alone (no rag_faq/rag_property) → authority=0 → abstain."""
    pool = _make_pool([_memory_item(), _memory_item()])
    eval_ = evaluate_evidence_pool(pool, action="answer_knowledge")
    assert eval_.should_abstain is True
    assert eval_.abstain_reason in ("low_confidence", "no_authoritative_source")
    assert eval_.authority == 0.0


# ── No-abstain cases ──────────────────────────────────────────────────────────

def test_rag_items_with_real_ids_no_abstain():
    """Good pool: rag_faq items with real source IDs → confident → no abstain."""
    pool = _make_pool([_rag_item(), _rag_item(id="2"), _rag_item(id="3")])
    eval_ = evaluate_evidence_pool(pool, action="answer_knowledge")
    assert eval_.should_abstain is False
    assert eval_.confidence >= ABSTAIN_THRESHOLD
    assert eval_.authoritative_items == 3


def test_non_knowledge_action_never_abstains():
    """Scheduling / search actions must never trigger abstention (no knowledge needed)."""
    for action in ("search_properties", "book_step", "smalltalk", "clarify_slot"):
        eval_ = evaluate_evidence_pool([], action=action)
        assert eval_.should_abstain is False, f"Unexpected abstain on action={action}"


def test_non_knowledge_with_empty_pool_no_abstain():
    eval_ = evaluate_evidence_pool([], action="search_properties")
    assert eval_.should_abstain is False
    assert eval_.confidence == pytest.approx(0.0, abs=0.01)  # all dims zero (consistency stub=0)


# ── Dimension scoring ─────────────────────────────────────────────────────────

def test_completeness_zero_when_no_items():
    eval_ = evaluate_evidence_pool([], action="search")
    assert eval_.completeness == 0.0


def test_completeness_one_when_has_items():
    pool = _make_pool([_rag_item()])
    eval_ = evaluate_evidence_pool(pool, action="search")
    assert eval_.completeness == 1.0


def test_depth_caps_at_one_with_three_or_more_substantive():
    pool = _make_pool([_rag_item(), _rag_item(id="2"), _rag_item(id="3"), _rag_item(id="4")])
    eval_ = evaluate_evidence_pool(pool, action="search")
    assert eval_.depth == 1.0


def test_depth_fractional_with_fewer_substantive():
    short_item = {"source": "rag_faq", "id": "1", "text": "short", "score": 0.8, "timestamp": ""}
    pool = _make_pool([short_item, short_item])  # text < 50 chars
    eval_ = evaluate_evidence_pool(pool, action="search")
    assert eval_.depth == 0.0


def test_authority_fraction_from_rag_sources():
    pool = _make_pool([
        _rag_item(source="rag_faq"),
        _memory_item(source="episodic"),
    ])
    eval_ = evaluate_evidence_pool(pool, action="search")
    assert eval_.authority == pytest.approx(0.5, abs=0.01)


def test_recency_fraction_with_timestamps():
    pool = _make_pool([
        _rag_item(),           # has timestamp
        _memory_item(),        # no timestamp
    ])
    eval_ = evaluate_evidence_pool(pool, action="search")
    assert eval_.recency == pytest.approx(0.5, abs=0.01)


def test_consistency_stub_zero():
    """Stub: consistency is 0.0 until KA5 adds real contradiction detection."""
    eval_ = evaluate_evidence_pool([], action="search")
    assert eval_.consistency == 0.0


# ── to_dict shape ─────────────────────────────────────────────────────────────

def test_to_dict_has_required_keys():
    eval_ = evaluate_evidence_pool(_make_pool([_rag_item()]), action="answer_knowledge")
    d = eval_.to_dict()
    for key in ("completeness", "depth", "authority", "recency", "consistency",
                "confidence", "should_abstain", "abstain_reason",
                "total_items", "authoritative_items"):
        assert key in d, f"Missing key: {key}"


# ── Abstention response ───────────────────────────────────────────────────────

def test_abstention_response_non_empty():
    assert isinstance(ABSTAIN_RESPONSE, str) and len(ABSTAIN_RESPONSE) > 20


def test_abstention_response_no_hallucination_markers():
    r = ABSTAIN_RESPONSE.lower()
    for bad in ("sí, tenemos", "claro que sí", "por supuesto", "tengo toda la info"):
        assert bad not in r, f"Hallucination marker found: '{bad}'"


if __name__ == "__main__":
    test_empty_pool_abstains_on_knowledge_action()
    test_rag_items_with_real_ids_no_abstain()
    test_non_knowledge_action_never_abstains()
    print("All KA3 self-checks passed.")
