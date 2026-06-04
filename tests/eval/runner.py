"""Replay cases through the ADAPTER path (not route_message directly).

Each case run uses a unique synthetic identity so per-case state never bleeds across
cases, and resets working memory on the first turn. The conversation within a case is
sequential and stateful (turn N sees turns 1..N-1), which is the point of multi-turn eval.

`process_turn_v2` / `process_turn_v3` need a live runtime (DB + Redis + OpenAI). This
runner is invoked by the owner against a running stack; it is not a unit test.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .graders import GraderResult, grade_turn, turn_passed
from .metrics import CaseRun
from .schema import Case

# An adapter: (phone, message, bsuid) -> result dict with the guaranteed-subset keys.
AdapterFn = Callable[[str, str, str | None], Awaitable[dict[str, Any]]]


def _get_adapter(router: str) -> AdapterFn:
    if router == "v2":
        from app.routers.v2_adapter import process_turn_v2

        async def _v2(phone: str, message: str, bsuid: str | None) -> dict[str, Any]:
            return await process_turn_v2(phone=phone, user_message=message, bsuid=bsuid)

        return _v2

    if router == "v3":
        from app.routers.v3.adapter import process_turn_v3  # type: ignore

        async def _v3(phone: str, message: str, bsuid: str | None) -> dict[str, Any]:
            return await process_turn_v3(  # type: ignore[call-arg]
                phone=phone, user_message=message, bsuid=bsuid, tenant=None
            )

        return _v3

    raise ValueError(f"unknown router {router!r}")


async def _reset(phone: str) -> None:
    try:
        from app.core.memory import memory_manager
        await memory_manager.reset_user_context(phone)
    except Exception:
        pass


async def run_case(case: Case, router: str, *, run_model: bool = True) -> CaseRun:
    """Execute one case once. Returns a CaseRun with pass/latency/cost/flags."""
    adapter = _get_adapter(router)
    # Unique identity per run → isolated state.
    phone = f"eval-{case.id}-{uuid.uuid4().hex[:8]}"
    await _reset(phone)

    latency_total = 0.0
    cost_total = 0.0
    human_flags = 0
    case_passed = True
    details: list[dict[str, Any]] = []

    from app.core.identity import set_current_contact

    for i, turn in enumerate(case.turns):
        set_current_contact(phone, None)
        t0 = time.perf_counter()
        try:
            result = await adapter(phone, turn.user, None)
        except Exception as e:  # an adapter exception fails the turn deterministically
            result = {"response_text": "", "tools_used": [], "rich_content": {},
                      "router_label": f"{router}::exception:{e}", "latency_ms": 0}
        wall_ms = (time.perf_counter() - t0) * 1000.0

        response = result.get("response_text", "") or ""
        tools = result.get("tools_used", []) or []
        rich = result.get("rich_content", {}) or {}
        latency_total += float(result.get("latency_ms") or wall_ms)

        graders: list[GraderResult] = await grade_turn(
            turn.expect, user=turn.user, response=response,
            tools=tools, rich=rich, run_model=run_model,
        )
        passed = turn_passed(graders)
        cost_total += sum(g.cost_usd for g in graders)
        human_flags += sum(1 for g in graders if g.human_flag)
        if not passed:
            case_passed = False

        judge = next((g.judge_score for g in graders if g.grader == "model"), None)
        details.append({
            "turn": i,
            "user": turn.user,
            "response": response,
            "tools": tools,
            "router_label": result.get("router_label"),
            "passed": passed,
            "judge_score": judge,
            "reasons": [reason for g in graders for reason in g.reasons if not g.passed],
        })

    return CaseRun(
        passed=case_passed,
        latency_ms_total=latency_total,
        cost_usd_total=cost_total,
        human_flags=human_flags,
        turn_details=details,
    )
