"""Progressive disclosure — selects skill detail level based on context.

Level 1 (summary, ~120 tokens): always loaded for all skills.
Level 2 (instructions, ~2K tokens): loaded when skill is relevant to current turn.
Level 3 (implementation, full code): loaded on execution.
"""

from app.skills.loader import SkillDefinition
from app.skills.registry import get_skill_registry


def get_context_tokens(
    skill_name: str | None = None, level: int = 1
) -> int:
    """Estimate token cost for loading skills at a given level.

    Args:
        skill_name: If set, count only that skill. If None, count all.
        level: Disclosure level (1, 2, or 3).

    Returns:
        Approximate token count.
    """
    registry = get_skill_registry()

    if skill_name:
        skill = registry.get(skill_name)
        if not skill:
            return 0
        return _token_count(skill, level)

    total = 0
    for skill in registry.skills.values():
        total += _token_count(skill, level)
    return total


def _token_count(skill: SkillDefinition, level: int) -> int:
    """Token count for a skill at a given level."""
    if level == 1:
        return skill.level1_tokens
    elif level == 2:
        return skill.level1_tokens + skill.level2_tokens
    else:
        return (
            skill.level1_tokens
            + skill.level2_tokens
            + len(skill.implementation.split())
        )


def select_level(
    skill_name: str,
    is_relevant: bool = False,
    is_executing: bool = False,
) -> int:
    """Decide which disclosure level to use.

    Default: Level 1 (summary only) — for 80% of turns.
    Level 2: when skill is relevant to the conversation.
    Level 3: when the skill is about to be executed.

    Args:
        skill_name: Name of the skill.
        is_relevant: The skill is relevant to the current turn.
        is_executing: The skill is about to be invoked.

    Returns:
        Disclosure level (1, 2, or 3).
    """
    if is_executing:
        return 3
    if is_relevant:
        return 2
    return 1


def get_active_skills_summary() -> str:
    """Build a compact summary of all skills for the system prompt.

    This is the Level 1 progressive disclosure — always injected.
    """
    registry = get_skill_registry()
    lines = []
    for skill in registry.skills.values():
        lines.append(f"- {skill.name}: {skill.description[:100]}")
    return "\n".join(lines)
