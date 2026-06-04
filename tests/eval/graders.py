"""Layered graders (eval-harness skill): code → rule → model → human.

- **code grader** — deterministic assertions over tools_used / rich_content
  (e.g. a booking exists IFF schedule_visit ran). Zero LLM, zero ambiguity.
- **rule grader** — regex/shape constraints on the response text.
- **model grader** — gpt-5.4-mini rubric judge (D7: same model, even for the judge),
  strict JSON output. Advisory only (D5) — LLM judges have self-preference bias.
- **human grader** — never auto-passes/fails; flags a turn for manual spot-check.

A turn passes when every *applicable* deterministic grader passes AND (if a rubric is
given) the model grader passes. Human flags don't fail a turn; they surface for review.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from .schema import Expectation

# gpt-5.4-mini price (USD per token). Unknown at authoring time → conservative default,
# overridable via env EVAL_JUDGE_INPUT_USD / EVAL_JUDGE_OUTPUT_USD. Cost is advisory.
_JUDGE_IN = float(os.environ.get("EVAL_JUDGE_INPUT_USD", "0.00000025"))
_JUDGE_OUT = float(os.environ.get("EVAL_JUDGE_OUTPUT_USD", "0.000002"))


@dataclass
class GraderResult:
    passed: bool
    grader: str
    reasons: list[str] = field(default_factory=list)
    human_flag: bool = False
    cost_usd: float = 0.0
    judge_score: float | None = None


def grade_code(expect: Expectation, tools: list[str], rich: dict[str, Any]) -> GraderResult:
    """Deterministic tool/selection/booking assertions."""
    reasons: list[str] = []
    tools_set = set(tools or [])

    for t in expect.tools_all:
        if t not in tools_set:
            reasons.append(f"missing required tool {t!r}")
    if expect.tools_any and not (tools_set & set(expect.tools_any)):
        reasons.append(f"none of expected tools ran: {expect.tools_any}")
    for t in expect.tools_none:
        if t in tools_set:
            reasons.append(f"forbidden tool ran: {t!r}")

    if expect.selection is not None:
        has_sel = bool((rich or {}).get("selected_property_id"))
        if has_sel != expect.selection:
            reasons.append(f"selection={has_sel}, expected {expect.selection}")

    if expect.booking is not None:
        booked = "schedule_visit" in tools_set
        if booked != expect.booking:
            reasons.append(f"booking={booked}, expected {expect.booking}")

    return GraderResult(passed=not reasons, grader="code", reasons=reasons)


def grade_rule(expect: Expectation, response: str) -> GraderResult:
    """Regex/shape constraints on the response text."""
    reasons: list[str] = []
    text = response or ""

    if expect.nonempty and not text.strip():
        reasons.append("response is empty")
    if expect.max_len is not None and len(text) > expect.max_len:
        reasons.append(f"response too long ({len(text)} > {expect.max_len})")
    if expect.regex_any and not any(re.search(p, text, re.I | re.S) for p in expect.regex_any):
        reasons.append(f"no regex_any matched: {expect.regex_any}")
    for p in expect.regex_none:
        if re.search(p, text, re.I | re.S):
            reasons.append(f"forbidden pattern matched: {p!r}")

    return GraderResult(passed=not reasons, grader="rule", reasons=reasons)


_JUDGE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "turn_judgement",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "task_completion": {"type": "boolean"},
                "faithful": {"type": "boolean"},
                "no_loop": {"type": "boolean"},
                "tone_ok": {"type": "boolean"},
                "score": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": [
                "task_completion", "faithful", "no_loop", "tone_ok", "score", "reason",
            ],
        },
    },
}

# Versioned + deterministic rubric prompt (eval-harness: keep graders deterministic).
_JUDGE_SYSTEM = (
    "Sos un evaluador estricto de un asistente inmobiliario por WhatsApp (es-AR). "
    "Juzgás UN turno del bot contra un criterio. Devolvés SOLO el JSON del schema. "
    "task_completion=cumple el criterio; faithful=sin inventar datos no provistos; "
    "no_loop=no repite ni vuelve a preguntar algo ya respondido; tone_ok=cordial y claro. "
    "score ∈ [0,1]. Sé determinista y conservador."
)
_JUDGE_VERSION = "judge-v1"


async def grade_model(expect: Expectation, user: str, response: str) -> GraderResult:
    """LLM rubric judge (gpt-5.4-mini, strict JSON). Advisory."""
    if not expect.rubric:
        return GraderResult(passed=True, grader="model", reasons=["no rubric"])
    try:
        from app.agents.cs_llm_client import LLMRole, get_client, get_model, max_tokens_kwarg

        client = get_client(LLMRole.CLASSIFY)
        model = get_model(LLMRole.CLASSIFY)  # D7: single model even for the judge
        user_prompt = (
            f"[{_JUDGE_VERSION}]\nCriterio de aprobación:\n{expect.rubric}\n\n"
            f"Mensaje del usuario:\n{user}\n\nRespuesta del bot:\n{response}"
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format=_JUDGE_SCHEMA,
            temperature=0,
            **max_tokens_kwarg(300, LLMRole.CLASSIFY),
        )
        import json as _json

        data = _json.loads(resp.choices[0].message.content or "{}")
        usage = getattr(resp, "usage", None)
        cost = 0.0
        if usage is not None:
            cost = (getattr(usage, "prompt_tokens", 0) * _JUDGE_IN
                    + getattr(usage, "completion_tokens", 0) * _JUDGE_OUT)
        passed = bool(
            data.get("task_completion") and data.get("faithful")
            and data.get("no_loop") and data.get("tone_ok")
        )
        reason = str(data.get("reason", ""))
        return GraderResult(
            passed=passed,
            grader="model",
            reasons=[] if passed else [f"judge: {reason}"],
            cost_usd=cost,
            judge_score=float(data.get("score", 0.0)),
        )
    except Exception as e:
        # Judge is advisory — its failure must not crash the run. Treat as non-fatal pass
        # with a flag so the row is reviewed, not silently trusted.
        return GraderResult(
            passed=True, grader="model", reasons=[f"judge error (ignored): {e}"],
            human_flag=True,
        )


async def grade_turn(
    expect: Expectation,
    *,
    user: str,
    response: str,
    tools: list[str],
    rich: dict[str, Any],
    run_model: bool = True,
) -> list[GraderResult]:
    """Run all applicable graders for one turn. Returns each grader's result."""
    results = [
        grade_code(expect, tools, rich),
        grade_rule(expect, response),
    ]
    if run_model and expect.rubric:
        results.append(await grade_model(expect, user, response))
    if expect.flag_human:
        results.append(GraderResult(
            passed=True, grader="human", reasons=["flagged for manual review"],
            human_flag=True,
        ))
    return results


def turn_passed(results: list[GraderResult]) -> bool:
    """A turn passes iff every grader (code/rule/model) passed. Human flags don't fail."""
    return all(r.passed for r in results if r.grader != "human")
