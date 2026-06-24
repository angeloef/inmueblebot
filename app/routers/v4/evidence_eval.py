"""V4 KA3 — Evidence evaluator + abstention signal (anti-hallucination).

Takes the evidence_pool produced by KA2 (list of {intent, args_hint, evidence})
and scores it on 5 dimensions before the LLM synthesises a response.

Design: fully deterministic, zero extra LLM calls, thresholded.
Upgrade path: if KA-EVAL shows the thresholds miss real cases, add
per-dimension overrides in tenant config before reaching for an LLM judge.

Abstention rule (hard): confidence < ABSTAIN_THRESHOLD on a knowledge-flavoured
action → caller must replace response with a clarification, not generate a claim.

The 5 dimensions (from the KA plan):
  1. completeness  — was there ANY evidence at all?
  2. depth         — how many substantive items (>50 chars)?
  3. recency       — fraction of items with a non-empty timestamp
  4. authority     — fraction of items from authoritative sources (rag_faq, rag_property)
  5. consistency   — reserved for future LLM-based cross-check; always 0.0 for now

ponytail: consistency=0.0 until KA5 adds real contradiction detection — inflating
it to 1.0 skews eval baselines by 0.05 without adding signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from loguru import logger

# Actions that require grounded evidence (knowledge-flavoured)
_KNOWLEDGE_ACTIONS = frozenset({
    "answer_knowledge", "answer_faq", "knowledge",
    "clarify",  # clarification still draws on evidence
})

# Sources considered authoritative (have source_id from a real KB row)
_AUTHORITATIVE_SOURCES = frozenset({"rag_faq", "rag_property"})

# Dimension weights must sum to 1.0
_W_COMPLETENESS = 0.40
_W_DEPTH = 0.30
_W_AUTHORITY = 0.20
_W_RECENCY = 0.05
_W_CONSISTENCY = 0.05

# Minimum confidence below which the agent must abstain on knowledge actions
ABSTAIN_THRESHOLD = 0.25

# Minimum text length to count an item as "substantive"
_DEPTH_MIN_CHARS = 50


@dataclass(frozen=True)
class EvidenceEvaluation:
    """Per-turn evidence quality assessment. Immutable."""

    # 5 dimension scores, each 0.0–1.0
    completeness: float
    depth: float
    authority: float
    recency: float
    consistency: float

    # Weighted aggregate
    confidence: float

    # Derived signal
    should_abstain: bool
    abstain_reason: str = ""

    # Raw counts for eval harness inspection
    total_items: int = 0
    authoritative_items: int = 0

    def to_dict(self) -> dict:
        return {
            "completeness": round(self.completeness, 4),
            "depth": round(self.depth, 4),
            "authority": round(self.authority, 4),
            "recency": round(self.recency, 4),
            "consistency": round(self.consistency, 4),
            "confidence": round(self.confidence, 4),
            "should_abstain": self.should_abstain,
            "abstain_reason": self.abstain_reason,
            "total_items": self.total_items,
            "authoritative_items": self.authoritative_items,
        }


def evaluate_evidence_pool(
    pool: list[dict],
    action: str,
    abstain_threshold: float = ABSTAIN_THRESHOLD,
) -> EvidenceEvaluation:
    """Score the evidence pool on 5 dimensions and decide whether to abstain.

    Args:
        pool: Output of build_evidence_pool() — list of
              {intent, args_hint, evidence: [{source, id, text, score, timestamp}]}.
        action: The LLM-chosen action for this turn (e.g. "answer_knowledge").
        abstain_threshold: Override the module constant in tests.

    Returns:
        EvidenceEvaluation with confidence and should_abstain flag.
    """
    is_knowledge_action = action in _KNOWLEDGE_ACTIONS

    # Flatten evidence across all sub-goals
    all_items: list[dict] = []
    for goal in (pool or []):
        ev = goal.get("evidence")
        if ev is None and goal:
            logger.warning("[V4/KA3] pool entry missing 'evidence' key: {}", list(goal.keys()))
        all_items.extend(ev or [])

    n = len(all_items)

    # ── Dimension 1: Completeness ─────────────────────────────────────────────
    completeness = 1.0 if n > 0 else 0.0

    # ── Dimension 2: Depth — substantive items / target of 3 ─────────────────
    # Target is a fixed count (≥3), not a fraction of n — one deep item is still
    # partial coverage, not full depth.
    substantive = sum(1 for it in all_items if len(str(it.get("text") or "")) > _DEPTH_MIN_CHARS)
    depth = min(substantive / 3.0, 1.0) if n > 0 else 0.0

    # ── Dimension 3: Authority — fraction from grounded sources ───────────────
    authoritative = sum(1 for it in all_items if it.get("source") in _AUTHORITATIVE_SOURCES)
    authority = authoritative / n if n > 0 else 0.0

    # ── Dimension 4: Recency — fraction with a non-empty timestamp ────────────
    with_ts = sum(1 for it in all_items if str(it.get("timestamp") or "").strip())
    recency = with_ts / n if n > 0 else 0.0

    # ── Dimension 5: Consistency — stub, 0.0 until KA5 adds detection ─────────
    consistency = 0.0

    # ── Weighted aggregate ────────────────────────────────────────────────────
    confidence = (
        completeness * _W_COMPLETENESS
        + depth * _W_DEPTH
        + authority * _W_AUTHORITY
        + recency * _W_RECENCY
        + consistency * _W_CONSISTENCY
    )

    # ── Abstention decision (only on knowledge-flavoured actions) ─────────────
    # Hard rule: knowledge claims MUST have at least one authoritative source
    # (rag_faq or rag_property). Memory alone cannot ground a property/FAQ claim.
    should_abstain = False
    abstain_reason = ""

    if is_knowledge_action:
        if completeness == 0.0:
            should_abstain = True
            abstain_reason = "no_evidence"
        elif authority == 0.0:
            should_abstain = True
            abstain_reason = "no_authoritative_source"
        elif confidence < abstain_threshold:
            should_abstain = True
            abstain_reason = "low_confidence"

    return EvidenceEvaluation(
        completeness=completeness,
        depth=depth,
        authority=authority,
        recency=recency,
        consistency=consistency,
        confidence=round(confidence, 4),
        should_abstain=should_abstain,
        abstain_reason=abstain_reason,
        total_items=n,
        authoritative_items=authoritative,
    )


# ── Abstention response ───────────────────────────────────────────────────────

ABSTAIN_RESPONSE = (
    "No tengo información específica sobre eso en nuestra base de datos. "
    "Para que no te dé datos incorrectos, te recomiendo consultarlo directamente "
    "con uno de nuestros asesores. ¿Puedo ayudarte con algo más?"
)
