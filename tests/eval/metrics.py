"""Pass-rate + cost/latency aggregation.

Definitions (per the build plan §0b targets):
  pass@1  — mean over every (case, run) of "did this single run pass?"
  pass@k  — CAPABILITY: fraction of cases where >=1 of k runs passed   (target >=0.90)
  pass^k  — CONSISTENCY/REGRESSION: fraction of cases where ALL k runs passed (target 1.00
            on release-critical flows)

Cost/latency drift is tracked alongside so quality-chasing can't silently blow D7's budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any


@dataclass
class CaseRun:
    """One execution of one case (k of them per case)."""
    passed: bool
    latency_ms_total: float
    cost_usd_total: float
    human_flags: int
    turn_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    split: str
    tags: list[str]
    runs: list[CaseRun]

    @property
    def pass_at_1(self) -> float:
        return mean(1.0 if r.passed else 0.0 for r in self.runs)

    @property
    def pass_at_k(self) -> bool:
        return any(r.passed for r in self.runs)

    @property
    def pass_pow_k(self) -> bool:
        return all(r.passed for r in self.runs)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1))))
    return s[idx]


def aggregate(results: list[CaseResult], k: int) -> dict[str, Any]:
    """Roll up case results into the headline metrics + cost/latency."""
    if not results:
        return {"cases": 0}

    all_latencies = [r.latency_ms_total for c in results for r in c.runs]
    all_costs = [r.cost_usd_total for c in results for r in c.runs]
    total_flags = sum(r.human_flags for c in results for r in c.runs)

    summary = {
        "cases": len(results),
        "k": k,
        "pass@1": round(mean(c.pass_at_1 for c in results), 4),
        f"pass@{k}": round(mean(1.0 if c.pass_at_k else 0.0 for c in results), 4),
        f"pass^{k}": round(mean(1.0 if c.pass_pow_k else 0.0 for c in results), 4),
        "latency_ms_mean": round(mean(all_latencies), 1) if all_latencies else 0.0,
        "latency_ms_p95": round(_percentile(all_latencies, 95), 1),
        "cost_usd_total": round(sum(all_costs), 6),
        "cost_usd_per_run_mean": round(mean(all_costs), 6) if all_costs else 0.0,
        "human_flags": total_flags,
        "failing_cases": sorted(c.case_id for c in results if not c.pass_pow_k),
    }
    return summary
