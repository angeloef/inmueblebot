"""Eval harness CLI.

Examples:
    # V2 baseline on the frozen hold-out, k=3, with the model grader:
    python -m tests.eval.run_eval --router v2 --split holdout --k 3

    # Snapshot the current V2 result as the baseline (dev + holdout):
    python -m tests.eval.run_eval --router v2 --split all --snapshot

    # Fast deterministic-only run (no LLM judge):
    python -m tests.eval.run_eval --router v2 --split dev --no-model --k 1

Needs a live runtime (DB + Redis + OPENAI_API_KEY) because it routes through the adapter.
Advisory only — promotion is manual (D5).
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from .metrics import CaseResult, aggregate
from .report import git_sha, markdown_diff, snapshot_baseline, write_report
from .runner import run_case
from .schema import load_cases


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    split = None if args.split == "all" else args.split
    cases = load_cases(split)
    if not cases:
        raise SystemExit(f"no cases for split={args.split!r}")

    results: list[CaseResult] = []
    for case in cases:
        runs = []
        for _ in range(args.k):
            runs.append(await run_case(case, args.router, run_model=not args.no_model))
        results.append(CaseResult(case.id, case.split, case.tags, runs))
        cr = results[-1]
        mark = "OK" if cr.pass_pow_k else ("~" if cr.pass_at_k else "FAIL")
        print(f"  [{mark:4s}] {case.id:30s} pass@1={cr.pass_at_1:.2f}")

    summary = aggregate(results, args.k)
    payload = {
        "meta": {
            "router": args.router,
            "split": args.split,
            "k": args.k,
            "run_model": not args.no_model,
            "sha": git_sha(),
        },
        "summary": summary,
        "cases": [
            {
                "id": c.case_id, "split": c.split, "tags": c.tags,
                "pass@1": round(c.pass_at_1, 4),
                "pass@k": c.pass_at_k, "pass^k": c.pass_pow_k,
                "runs": [r.turn_details for r in c.runs],
            }
            for c in results
        ],
    }
    return payload


def main() -> None:
    p = argparse.ArgumentParser(description="InmuebleBot router eval harness")
    p.add_argument("--router", default="v2", choices=["v2", "v3"])
    p.add_argument("--split", default="holdout", choices=["dev", "holdout", "all"])
    p.add_argument("--k", type=int, default=3, help="runs per case (pass@k / pass^k)")
    p.add_argument("--no-model", action="store_true", help="skip the LLM rubric judge")
    p.add_argument("--snapshot", action="store_true",
                   help="also write this run as baseline-v2.json")
    args = p.parse_args()

    payload = asyncio.run(_run(args))

    out = write_report(payload)
    print(f"\n{markdown_diff(payload)}\n")
    print(f"report → {out}")
    if args.snapshot:
        base = snapshot_baseline(payload)
        print(f"baseline snapshot → {base}")


if __name__ == "__main__":
    main()
