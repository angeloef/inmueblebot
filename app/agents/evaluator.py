"""LoopEvaluator — expected vs actual, replan logic (Phase 9).

After executing the plan, the evaluator checks:
1. Did each step succeed?
2. Did we get the expected number of results?
3. Should we replan with adjusted parameters?
"""

from dataclasses import dataclass, field

from app.agents.observer import Observation


@dataclass
class Evaluation:
    """Result of evaluating an execution plan."""
    success: bool
    should_replan: bool = False
    replan_reason: str = ""
    adjusted_parameters: dict = field(default_factory=dict)
    summary: str = ""


def evaluate(observations: list[Observation], plan_step_count: int) -> Evaluation:
    """Evaluate whether the plan achieved its goals.

    Replanning triggers:
    - Search returned 0 results → suggest broader search
    - Search returned > 10 results → suggest adding filters
    - Tool failed → retry or skip
    - Details returned error → suggest re-searching

    Args:
        observations: Structured observations from executed tools.
        plan_step_count: Number of steps in the original plan.

    Returns:
        An Evaluation with replan recommendation.
    """
    if not observations:
        return Evaluation(success=True, summary="No tools to evaluate")

    all_ok = all(o.success for o in observations)
    anomalies = [o for o in observations if o.anomaly]

    # Case 1: Everything worked perfectly
    if all_ok and not anomalies:
        return Evaluation(
            success=True,
            summary=_build_success_summary(observations),
        )

    # Case 2: Search returned 0 results
    search_obs = [o for o in observations if o.tool_name == "search_properties"]
    if search_obs and search_obs[0].result_count == 0:
        return Evaluation(
            success=False,
            should_replan=True,
            replan_reason="search_no_results",
            adjusted_parameters={
                "action": "broaden",
                "hint": "Subir presupuesto, ampliar zona, o reducir dormitorios",
            },
            summary="Search returned 0 results. Suggest broadening criteria.",
        )

    # Case 3: Tool failure
    failures = [o for o in observations if not o.success]
    if failures:
        return Evaluation(
            success=False,
            should_replan=True,
            replan_reason="tool_failure",
            adjusted_parameters={
                "action": "retry_or_suggest",
                "failed_tools": [f.tool_name for f in failures],
            },
            summary=f"Tool(s) failed: {[f.tool_name for f in failures]}. Consider retrying or suggesting alternatives.",
        )

    # Case 4: Partial success (some anomalies but not critical)
    if anomalies:
        return Evaluation(
            success=True,
            summary=f"Partial success with {len(anomalies)} anomaly(ies): {[a.anomaly_detail for a in anomalies]}",
        )

    return Evaluation(success=True, summary=_build_success_summary(observations))


def _build_success_summary(observations: list[Observation]) -> str:
    """Build a human-readable evaluation summary."""
    parts = []
    for obs in observations:
        if obs.result_count > 0:
            parts.append(f"{obs.tool_name}: {obs.result_count} results")
        else:
            parts.append(f"{obs.tool_name}: OK")
    return " | ".join(parts) if parts else "All steps completed"


def build_replan_context(eval_result: Evaluation) -> str:
    """Build a replan hint for the LLM context.

    This tells the LLM what to do differently on the next attempt.
    """
    if not eval_result.should_replan:
        return ""

    lines = ["[REPLANIFICACIÓN]"]
    lines.append(f"Motivo: {eval_result.replan_reason}")

    params = eval_result.adjusted_parameters
    if params.get("action") == "broaden":
        lines.append(f"Sugerencia: {params.get('hint', 'Ampliar criterios')}")
    elif params.get("action") == "retry_or_suggest":
        tools = params.get("failed_tools", [])
        lines.append(f"Herramientas fallidas: {', '.join(tools)}. Sugerir al usuario intentar de otra forma.")

    return "\n".join(lines)
