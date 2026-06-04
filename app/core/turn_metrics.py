"""Per-turn structured observability (Phase 0b).

Emits exactly ONE JSON line per processed turn so router behavior, cost and latency
are measurable BEFORE we change behavior in V3. Decoupled and fully defensive: a
metrics failure must never break a turn (V2 stays green).

Fields (a turn fills whatever it knows; the rest stay null):
    tenant_id, router, router_label, action, tools, latency_ms,
    prompt_tokens, completion_tokens, cache_hit, cost_usd,
    confidence, extraction_source, judge_score

V2 populates router_label/tools/latency_ms/confidence; V3 will fill the rest
(action, token counts, cache_hit, cost_usd, extraction_source, judge_score).
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

# Stable key order so log post-processing / greps are predictable.
_FIELDS = (
    "tenant_id",
    "router",
    "router_label",
    "action",
    "tools",
    "latency_ms",
    "prompt_tokens",
    "completion_tokens",
    "cache_hit",
    "cost_usd",
    "confidence",
    "extraction_source",
    "judge_score",
)

# Marker prefix so a log shipper can select turn-metric lines deterministically.
_MARKER = "TURN_METRICS"


def emit_turn_metrics(
    *,
    router: str,
    tenant_id: str | None = None,
    router_label: str | None = None,
    action: str | None = None,
    tools: list[str] | None = None,
    latency_ms: float | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cache_hit: bool | None = None,
    cost_usd: float | None = None,
    confidence: float | None = None,
    extraction_source: str | None = None,
    judge_score: float | None = None,
) -> None:
    """Log one JSON line of turn metrics. Never raises."""
    try:
        record: dict[str, Any] = {
            "tenant_id": tenant_id,
            "router": router,
            "router_label": router_label,
            "action": action,
            "tools": tools or [],
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cache_hit": cache_hit,
            "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
            "confidence": round(confidence, 4) if confidence is not None else None,
            "extraction_source": extraction_source,
            "judge_score": judge_score,
        }
        # Guarantee key order + only known fields.
        ordered = {k: record.get(k) for k in _FIELDS}
        logger.info("{} {}", _MARKER, json.dumps(ordered, ensure_ascii=False))
    except Exception:  # pragma: no cover - observability must never break a turn
        logger.opt(exception=True).debug("emit_turn_metrics failed (ignored)")
