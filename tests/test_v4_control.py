"""Tests for V4 KA5 — control loop + write-back.

Offline: decide_next is pure; run_retrieval_loop is exercised by monkeypatching
the RAG gather; write_back is checked for idempotent reuse + fail-closed safety.
"""

from __future__ import annotations

import pytest

from app.routers.v4 import control as v4_control
from app.routers.v4.control import ControlDecision, decide_next, MAX_RETRIEVE_ITERS
from app.routers.v4.evidence_eval import evaluate_evidence_pool


def _good_pool() -> list[dict]:
    item = {"source": "rag_faq", "id": "1", "text": "x" * 60, "score": 0.9, "timestamp": "2026-06-24"}
    return [{"intent": "knowledge", "args_hint": "{}", "evidence": [item, {**item, "id": "2"}, {**item, "id": "3"}]}]


# ── decide_next (pure) ──────────────────────────────────────────────────────────

def test_decide_respond_when_evidence_is_good():
    ev = evaluate_evidence_pool(_good_pool(), action="answer_knowledge")
    assert ev.should_abstain is False
    assert decide_next(ev, iters_done=0) is ControlDecision.RESPOND


def test_decide_retrieve_more_when_would_abstain_with_budget():
    ev = evaluate_evidence_pool([], action="answer_knowledge")  # no evidence → abstain
    assert ev.should_abstain is True
    assert decide_next(ev, iters_done=0) is ControlDecision.RETRIEVE_MORE


def test_decide_abstain_when_budget_exhausted():
    ev = evaluate_evidence_pool([], action="answer_knowledge")
    assert decide_next(ev, iters_done=MAX_RETRIEVE_ITERS) is ControlDecision.ABSTAIN


# ── run_retrieval_loop ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_loop_retries_then_recovers(monkeypatch):
    """First pass finds nothing (abstain) → loop retries → second pass grounds it."""
    calls = {"n": 0}

    async def fake_gather(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return []  # premature empty
        from app.routers.v4.evidence import EvidenceItem
        return [EvidenceItem(source="rag_faq", id="1", text="x" * 60, score=0.9, timestamp="2026-06-24")]

    import app.routers.v4.evidence as v4_evidence
    monkeypatch.setattr(v4_evidence, "gather_rag_evidence", fake_gather)

    pool, ev, iters, rag = await v4_control.run_retrieval_loop(
        sub_goals=[{"intent": "knowledge", "args_hint": "{}"}],
        memory_items=[],
        action="answer_knowledge",
        tenant_id="t",
        query="requisitos de alquiler",
        base_threshold=0.5,
        rag_limit=5,
        is_knowledge_turn=True,
    )
    assert iters == 1
    assert ev.should_abstain is False
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_loop_caps_iterations_and_abstains(monkeypatch):
    """Persistent empty retrieval → loop stops at the cap and abstains."""
    calls = {"n": 0}

    async def fake_gather(**kwargs):
        calls["n"] += 1
        return []

    import app.routers.v4.evidence as v4_evidence
    monkeypatch.setattr(v4_evidence, "gather_rag_evidence", fake_gather)

    pool, ev, iters, rag = await v4_control.run_retrieval_loop(
        sub_goals=[{"intent": "knowledge", "args_hint": "{}"}],
        memory_items=[],
        action="answer_knowledge",
        tenant_id="t",
        query="algo inexistente",
        base_threshold=0.5,
        rag_limit=5,
        is_knowledge_turn=True,
    )
    assert iters == MAX_RETRIEVE_ITERS
    assert ev.should_abstain is True
    assert calls["n"] == MAX_RETRIEVE_ITERS + 1  # initial pass + retries


@pytest.mark.asyncio
async def test_loop_skips_rag_on_non_knowledge_turn(monkeypatch):
    """Non-knowledge turn → no RAG call, no abstain, zero retries."""
    async def fake_gather(**kwargs):  # pragma: no cover - must not run
        raise AssertionError("RAG should not be called on a non-knowledge turn")

    import app.routers.v4.evidence as v4_evidence
    monkeypatch.setattr(v4_evidence, "gather_rag_evidence", fake_gather)

    pool, ev, iters, rag = await v4_control.run_retrieval_loop(
        sub_goals=[{"intent": "scheduling", "args_hint": "{}"}],
        memory_items=[],
        action="book_step",
        tenant_id="t",
        query="quiero agendar",
        base_threshold=0.5,
        rag_limit=5,
        is_knowledge_turn=False,
    )
    assert iters == 0
    assert ev.should_abstain is False


# ── write_back ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_back_delegates_to_consolidation(monkeypatch):
    captured = {}

    async def fake_consolidate(belief, phone=""):
        captured["belief"] = belief
        captured["phone"] = phone
        return {}

    import app.memory.consolidation as consolidation
    monkeypatch.setattr(consolidation, "consolidate_session", fake_consolidate)

    sentinel = object()
    await v4_control.write_back(sentinel, "549111")
    assert captured["belief"] is sentinel
    assert captured["phone"] == "549111"


@pytest.mark.asyncio
async def test_write_back_is_fail_closed(monkeypatch):
    async def boom(belief, phone=""):
        raise RuntimeError("redis down")

    import app.memory.consolidation as consolidation
    monkeypatch.setattr(consolidation, "consolidate_session", boom)

    # Must not raise — a write-back failure cannot break the turn.
    await v4_control.write_back(object(), "549111")
