"""Report writers: reports/<git-sha>.json + a markdown diff vs the V2 baseline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

REPORTS_DIR = Path(__file__).parent / "reports"
BASELINE_PATH = Path(__file__).parent / "baseline-v2.json"


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "nogit"


def write_report(payload: dict[str, Any], sha: str | None = None) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    sha = sha or git_sha()
    out = REPORTS_DIR / f"{sha}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def snapshot_baseline(payload: dict[str, Any]) -> Path:
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return BASELINE_PATH


def load_baseline() -> dict[str, Any] | None:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return None


def _fmt_delta(cur: float, base: float | None) -> str:
    if base is None:
        return f"{cur}"
    d = cur - base
    arrow = "→" if abs(d) < 1e-9 else ("▲" if d > 0 else "▼")
    return f"{cur} ({arrow} {d:+.4f} vs {base})"


def markdown_diff(payload: dict[str, Any]) -> str:
    """Human-readable summary with deltas vs baseline (if present)."""
    summary = payload["summary"]
    base = (load_baseline() or {}).get("summary", {})
    k = summary.get("k", 3)
    lines = [
        f"# Eval report — router={payload['meta']['router']} "
        f"split={payload['meta']['split']} sha={payload['meta']['sha']}",
        "",
        f"- cases: {summary.get('cases')}  ·  k: {k}  ·  model_grader: "
        f"{payload['meta']['run_model']}",
        "",
        "| metric | value (Δ vs baseline) |",
        "|---|---|",
        f"| pass@1 | {_fmt_delta(summary.get('pass@1', 0), base.get('pass@1'))} |",
        f"| pass@{k} (capability) | {_fmt_delta(summary.get(f'pass@{k}', 0), base.get(f'pass@{k}'))} |",
        f"| pass^{k} (regression) | {_fmt_delta(summary.get(f'pass^{k}', 0), base.get(f'pass^{k}'))} |",
        f"| latency_ms_mean | {_fmt_delta(summary.get('latency_ms_mean', 0), base.get('latency_ms_mean'))} |",
        f"| latency_ms_p95 | {_fmt_delta(summary.get('latency_ms_p95', 0), base.get('latency_ms_p95'))} |",
        f"| cost_usd_total | {_fmt_delta(summary.get('cost_usd_total', 0), base.get('cost_usd_total'))} |",
        f"| human_flags | {summary.get('human_flags', 0)} |",
        "",
    ]
    failing = summary.get("failing_cases", [])
    if failing:
        lines.append(f"**Failing cases ({len(failing)}):** {', '.join(failing)}")
    else:
        lines.append("**All cases passed pass^k. ✅**")
    return "\n".join(lines)
