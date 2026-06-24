"""V4 KA5 — bounded control loop + per-turn memory write-back.

Two pieces, both deterministic and cheap (no extra chat calls):

  - decide_next() / run_retrieval_loop(): the control loop. A simple decision
    machine over signals KA1/KA3 already produced — respond / retrieve-more /
    abstain. Handoff is decided earlier (safety gates + scheduling FSM), not here.
    "retrieve-more" widens the RAG threshold and tries ONE more retrieval pass
    before a knowledge turn abstains, recovering from premature abstention with
    a vector-retrieval call only (within the KA cost discipline).

  - write_back(): after the turn, refresh the session episode + accumulate the
    user persona so the NEXT turn/session actually recalls context. KA2's
    gather_memory_evidence reads exactly what this writes — this closes the
    cross-session memory loop that V3 left open (consolidate_session was never
    wired into the live path).

ponytail: MAX_RETRIEVE_ITERS is a fixed global; make it adaptive only if
KA-EVAL shows the cost/quality trade-off needs it.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from loguru import logger

if TYPE_CHECKING:
    from app.routers.v4.belief import BeliefStateV6
    from app.routers.v4.evidence_eval import EvidenceEvaluation

# Max extra retrieval passes before giving up and abstaining (fixed global cap).
MAX_RETRIEVE_ITERS = 1
# Threshold multiplier per retry pass — lower threshold = wider recall.
_WIDEN_FACTOR = 0.6


class ControlDecision(str, Enum):
    RESPOND = "respond"
    RETRIEVE_MORE = "retrieve_more"
    ABSTAIN = "abstain"


def decide_next(
    evidence_eval: EvidenceEvaluation,
    iters_done: int,
    max_iters: int = MAX_RETRIEVE_ITERS,
) -> ControlDecision:
    """Pure decision over the evidence evaluation (KA3) + how many passes we ran.

    KA3 only ever sets should_abstain on knowledge-flavoured actions, so this
    function is action-agnostic: good evidence → respond; would-abstain but we
    still have retrieval budget → retrieve-more; out of budget → abstain.
    """
    if not evidence_eval.should_abstain:
        return ControlDecision.RESPOND
    if iters_done < max_iters:
        return ControlDecision.RETRIEVE_MORE
    return ControlDecision.ABSTAIN


async def run_retrieval_loop(
    *,
    sub_goals: list[dict],
    memory_items: list,
    action: str,
    tenant_id: UUID | None,
    query: str,
    base_threshold: float,
    rag_limit: int,
    is_knowledge_turn: bool,
) -> tuple[list[dict], EvidenceEvaluation, int, list]:
    """Bounded retrieve→evaluate loop.

    Returns (evidence_pool, evidence_eval, iters_done, rag_items). Never raises:
    a retrieval failure leaves rag_items as-is and the loop falls through to the
    evaluation, which will abstain if there is genuinely no grounding.
    """
    from app.routers.v4 import evidence as v4_evidence
    from app.routers.v4.evidence_eval import evaluate_evidence_pool

    rag_items: list = []
    threshold = base_threshold
    iters = 0

    while True:
        if is_knowledge_turn:
            try:
                rag_items = await v4_evidence.gather_rag_evidence(
                    tenant_id=tenant_id,
                    query=query,
                    limit=rag_limit,
                    threshold=threshold,
                )
            except Exception as exc:
                logger.warning("[V4/KA5] gather_rag_evidence failed (non-fatal): {}", str(exc))

        pool = v4_evidence.build_evidence_pool(sub_goals, memory_items, rag_items)
        ev = evaluate_evidence_pool(pool, action)

        if decide_next(ev, iters) is not ControlDecision.RETRIEVE_MORE:
            return pool, ev, iters, rag_items

        iters += 1
        threshold = round(threshold * _WIDEN_FACTOR, 4)
        logger.debug("[V4/KA5] retrieve-more pass {} (threshold→{})", iters, threshold)


async def write_back(belief: BeliefStateV6, phone: str) -> None:
    """Per-turn memory write-back: refresh episode + accumulate persona + zone.

    Reuses the existing consolidation pipeline (DRY). Idempotent per session:
    save_episode upserts on session_id and dedups the Redis cache, so calling
    this every turn keeps the session's episode current instead of duplicating.

    ponytail: persona frequency counters over-weight slightly when written per
    turn rather than per session; the direction is still correct and KA2 only
    reads the top-3. Gate by session-end if KA-EVAL ever shows the skew matters.

    Never raises — a write-back failure must not break the turn.
    """
    try:
        from app.memory.consolidation import consolidate_session

        await consolidate_session(belief, phone=phone)
    except Exception as exc:
        logger.warning("[V4/KA5] write_back failed (non-fatal): {}", str(exc))
