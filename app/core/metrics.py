"""Metrics collection — latency histograms, routing stats, error rates (Phase 11)."""

import time
from collections import defaultdict


_metrics: dict = {
    "requests": 0,
    "errors": 0,
    "routing": defaultdict(int),
    "latencies_ms": [],
    "tool_calls": defaultdict(int),
    "start_time": time.time(),
}


def record_request(
    router: str,
    latency_ms: float,
    tools_called: list[str],
    is_error: bool = False,
) -> None:
    """Record a single request's metrics."""
    _metrics["requests"] += 1
    _metrics["routing"][router] += 1
    _metrics["latencies_ms"].append(latency_ms)

    for tool in tools_called:
        _metrics["tool_calls"][tool] += 1

    if is_error:
        _metrics["errors"] += 1

    # Keep only last 1000 latencies
    if len(_metrics["latencies_ms"]) > 1000:
        _metrics["latencies_ms"] = _metrics["latencies_ms"][-1000:]


def get_metrics() -> dict:
    """Get current metrics summary."""
    latencies = _metrics["latencies_ms"]
    if latencies:
        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[len(latencies_sorted) // 2]
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
        p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    else:
        p50 = p95 = p99 = 0

    uptime = time.time() - _metrics["start_time"]

    return {
        "uptime_seconds": round(uptime),
        "total_requests": _metrics["requests"],
        "error_count": _metrics["errors"],
        "error_rate": round(_metrics["errors"] / max(1, _metrics["requests"]), 4),
        "routing": dict(_metrics["routing"]),
        "tool_calls": dict(_metrics["tool_calls"]),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
    }
