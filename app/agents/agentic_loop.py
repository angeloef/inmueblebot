"""AgenticLoop — full Plan→Act→Observe→Evaluate cycle (Phase 9).

Orchestrates the complete agentic reasoning cycle:
1. THINK: Hidden CoT analysis
2. PLAN: Build tool execution sequence
3. ACT: Execute tools in order
4. OBSERVE: Parse and structure results
5. EVALUATE: Check success, decide replan

The thinking is always hidden from the user. Only the final response is shown.
"""

from app.agents.schemas import CSAgentResponse as AgentResponse, CSStructuredToolCall
from app.agents.thinking import think, summarize_thinking
from app.agents.planner import build_plan, ExecutionPlan
from app.agents.observer import observe, build_observation_report, Observation
from app.agents.evaluator import evaluate, build_replan_context, Evaluation
from app.agents.escalation import assess_confidence, build_clarification_message
from app.core.response_parser import parse_llm_response
from app.tools.v2.registry import execute_tool, get_tools_schema


async def run_agentic_loop(
    message: str,
    session_id: str,
    context_prompt: str = "",
    belief_summary: str = "",
    available_tools: list[str] | None = None,
) -> AgentResponse:
    """Execute the full Plan→Act→Observe→Evaluate agentic cycle.

    Args:
        message: User's message.
        session_id: Session identifier.
        context_prompt: Belief state context for LLM.
        belief_summary: Compact belief summary for thinking.
        available_tools: Subset of tools (for specialist mode). None = all.

    Returns:
        AgentResponse with the final response, tool history, and confidence.
    """
    all_tools = get_tools_schema()
    if available_tools is not None:
        allowed = set(available_tools)
        filtered_tools = [t for t in all_tools if t["function"]["name"] in allowed]
    else:
        filtered_tools = all_tools

    tool_names = [t["function"]["name"] for t in filtered_tools]
    all_tools_called: list[str] = []
    all_observations: list[Observation] = []
    all_results: list[dict] = []

    # ── PHASE 1: THINK ───────────────────────────────────────
    thinking = await think(message, context_prompt, belief_summary)
    thinking_summary = summarize_thinking(thinking)

    # ── PHASE 2: PLAN ────────────────────────────────────────
    plan = build_plan(thinking, tool_names, belief_summary)

    # ── PHASE 3-4: ACT + OBSERVE ─────────────────────────────
    import json as _json
    for step in plan.steps:
        tc = CSStructuredToolCall(
            id=f"plan_{step.tool_name}",
            name=step.tool_name,
            arguments=step.arguments,
        )
        result = await execute_tool(tc)
        all_tools_called.append(step.tool_name)
        all_results.append({"name": step.tool_name, "result": result})

        obs = observe(step.tool_name, str(result))
        all_observations.append(obs)

    # ── PHASE 5: EVALUATE ───────────────────────────────────
    evaluation = evaluate(all_observations, len(plan.steps))
    obs_report = build_observation_report(all_observations)

    # ── Generate final response ──────────────────────────────
    from app.agents.cs_llm_client import get_client, get_model

    client = get_client()

    # Build the system prompt with all context
    system_parts = []

    if thinking:
        system_parts.append(f"[RAZONAMIENTO INTERNO]\n{thinking}")
    system_parts.append(obs_report)

    if evaluation.should_replan:
        replan_ctx = build_replan_context(evaluation)
        system_parts.append(replan_ctx)
        system_parts.append(
            "INSTRUCCIÓN: La búsqueda no encontró resultados. "
            "Sugerí al usuario ajustar los filtros (subir presupuesto, "
            "ampliar zona, reducir dormitorios). NO vuelvas a buscar automáticamente."
        )

    system_parts.append(
        "Ahora respondé al usuario con el formato JSON habitual: "
        '{"respuesta": "...", "confianza": 0.XX}'
    )

    system_content = "\n\n".join(system_parts)
    if context_prompt:
        system_content = context_prompt + "\n\n" + system_content

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    # Add tool results to context if any
    for i, step in enumerate(plan.steps):
        if i < len(all_results):
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"plan_{step.tool_name}",
                    "type": "function",
                    "function": {"name": step.tool_name, "arguments": "{}"},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": f"plan_{step.tool_name}",
                "content": str(all_results[i]["result"]),
            })

    # Final LLM call to synthesize response
    final_response = await client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=0.3,
        max_completion_tokens=512,
    )

    raw_text = final_response.choices[0].message.content or ""
    final_text, raw_confidence = parse_llm_response(raw_text)
    level, confidence = assess_confidence(raw_confidence)
    escalated_text = build_clarification_message(level, final_text)

    return AgentResponse(
        response=escalated_text,
        tools_called=all_tools_called,
        raw_tool_results=[
            {"name": r["name"], "result": r["result"]}
            for r in all_results
        ],
        confidence=confidence,
    )
