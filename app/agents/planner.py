"""ToolPlanner — sequences tool calls with dependencies (Phase 9).

Analyzes the hidden CoT to determine which tools to call and in what order.
Handles tool dependencies (e.g., search before details, details before photos).
"""

from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """A single step in the execution plan."""
    tool_name: str
    arguments: dict = field(default_factory=dict)
    depends_on: str = ""  # name of previous step this depends on
    expected_outcome: str = ""


@dataclass
class ExecutionPlan:
    """A sequence of tool steps with dependencies."""
    steps: list[PlanStep] = field(default_factory=list)
    reasoning: str = ""
    fallback: str = ""  # What to do if the plan fails


def build_plan(
    thinking: str,
    available_tools: list[str],
    belief_context: str = "",
) -> ExecutionPlan:
    """Build an execution plan from the hidden CoT thinking.

    Uses rule-based heuristics to determine tool dependencies:
    - search_properties → get_property_details → get_property_images
    - get_property_details → schedule_visit

    Args:
        thinking: Hidden CoT output from the thinking phase.
        available_tools: Subset of tools the specialist can use.
        belief_context: Current belief state summary.

    Returns:
        An ExecutionPlan with ordered steps.
    """
    plan = ExecutionPlan(reasoning=thinking)

    thinking_lower = thinking.lower()

    # Detect tool sequences from thinking
    tool_order = _detect_tool_sequence(thinking_lower, available_tools)

    for i, tool_name in enumerate(tool_order):
        step = PlanStep(tool_name=tool_name, arguments={})

        # Add dependencies
        if tool_name == "get_property_details" and "search_properties" in [s.tool_name for s in plan.steps]:
            step.depends_on = "search_properties"
            step.expected_outcome = "Detailed property card with all fields"

        if tool_name == "get_property_images" and "get_property_details" in [s.tool_name for s in plan.steps]:
            step.depends_on = "get_property_details"
            step.expected_outcome = "List of image URLs"

        if tool_name == "schedule_visit" and "get_property_details" in [s.tool_name for s in plan.steps]:
            step.depends_on = "get_property_details"

        if tool_name == "search_properties":
            step.expected_outcome = "List of matching properties with IDs"

        if tool_name == "get_faq_answer":
            step.expected_outcome = "FAQ answer text"

        plan.steps.append(step)

    # Fallback
    if plan.steps:
        first_tool = plan.steps[0].tool_name
        plan.fallback = f"If {first_tool} fails or returns no results, suggest adjusting filters."
    else:
        plan.fallback = "Respond directly without tools."

    return plan


def _detect_tool_sequence(thinking: str, available: list[str]) -> list[str]:
    """Detect which tools should be called from the thinking text."""
    available_set = set(available)
    sequence = []

    # Priority order for common workflows
    priority_order = [
        "search_properties",
        "get_property_details",
        "get_property_images",
        "get_faq_answer",
        "schedule_visit",
    ]

    for tool in priority_order:
        if tool in available_set and _tool_mentioned(thinking, tool):
            sequence.append(tool)

    return sequence[:3]  # Max 3 steps per plan


def _tool_mentioned(thinking: str, tool_name: str) -> bool:
    """Check if a tool is mentioned in the thinking text."""
    keywords = {
        "search_properties": ["buscar", "search", "búsqueda", "propiedades", "resultados"],
        "get_property_details": ["detalle", "detail", "más info", "ficha", "específic"],
        "get_property_images": ["foto", "imagen", "photo", "image", "ver"],
        "get_faq_answer": ["faq", "requisito", "garantía", "pregunta", "frecuente"],
        "schedule_visit": ["agendar", "visita", "schedule", "coordinar"],
    }

    name_lower = tool_name.lower()
    if name_lower in thinking:
        return True

    for kw in keywords.get(tool_name, []):
        if kw in thinking:
            return True

    return False
