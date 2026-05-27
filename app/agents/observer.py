"""ToolObserver — parses tool results and extracts structured observations (Phase 9).

Analyzes tool outputs to extract counts, IDs, patterns, and anomalies.
Updates belief state with observations.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Observation:
    """Structured observation from a tool result."""
    tool_name: str
    success: bool
    result_count: int = 0
    result_ids: list[int] = field(default_factory=list)
    summary: str = ""
    anomaly: bool = False
    anomaly_detail: str = ""


def observe(tool_name: str, result: str) -> Observation:
    """Parse a tool result into a structured observation.

    Extracts:
    - Success/failure
    - Result count (e.g., "Encontré 5 propiedades")
    - Property IDs
    - Anomalies (errors, empty results, unexpected formats)
    """
    obs = Observation(tool_name=tool_name, success=True)

    if not result or "Error" in result[:50]:
        obs.success = False
        obs.anomaly = True
        obs.anomaly_detail = result[:200]
        obs.summary = f"Error in {tool_name}: {result[:100]}"
        return obs

    # Extract result count
    count_match = re.search(r"(?:Encontré|Encontré|Hay)\s+(\d+)\s+(?:propiedades|resultados|opciones)", result)
    if count_match:
        obs.result_count = int(count_match.group(1))

    # Extract property IDs
    id_matches = re.findall(r"\[(\d+)\]", result)
    obs.result_ids = [int(x) for x in id_matches]

    # Detect anomalies
    if "no encontré" in result.lower() or "no hay" in result.lower():
        obs.anomaly = True
        obs.anomaly_detail = "No results found"
        obs.summary = result[:200]
    elif obs.result_count == 0 and tool_name == "search_properties":
        obs.anomaly = True
        obs.anomaly_detail = "Zero search results"

    # Summary
    if not obs.summary:
        if obs.result_count > 0:
            obs.summary = f"{tool_name}: {obs.result_count} results, IDs: {obs.result_ids[:5]}"
        else:
            obs.summary = f"{tool_name}: completed successfully"

    return obs


def build_observation_report(observations: list[Observation]) -> str:
    """Build a compact observation report for the evaluator and replanning.

    This is injected into the LLM context so it can decide whether to replan.
    """
    if not observations:
        return "[No tool calls made]"

    lines = ["[OBSERVACIONES DE HERRAMIENTAS]"]
    for obs in observations:
        status = "✅" if obs.success else "❌"
        line = f"  {status} {obs.tool_name}"
        if obs.result_count > 0:
            line += f" → {obs.result_count} resultados"
        if obs.result_ids:
            line += f" | IDs: {obs.result_ids[:5]}"
        if obs.anomaly:
            line += f" | ⚠️ {obs.anomaly_detail}"
        lines.append(line)

    return "\n".join(lines)
