"""Skill registry — manages loaded skills, hot-reload, and tool schema generation."""

import time
from pathlib import Path
from typing import Optional

from app.skills.loader import SkillDefinition, load_all_skills, load_skill


class SkillRegistry:
    """Central registry for all loaded skills.

    Supports hot-reload: detect changed SKILL.md files and reload them
    without restarting the server.
    """

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, SkillDefinition] = {}
        self._mtimes: dict[str, float] = {}
        self._loaded_at: float = 0.0

    @property
    def skills(self) -> dict[str, SkillDefinition]:
        """All loaded skills by name."""
        return self._skills

    @property
    def count(self) -> int:
        return len(self._skills)

    def load_all(self) -> int:
        """Load all SKILL.md files from the skills directory."""
        loaded = load_all_skills(self.skills_dir)
        self._skills = {s.name: s for s in loaded}

        # Track modification times for hot-reload
        for s in loaded:
            path = Path(s.path)
            if path.exists():
                self._mtimes[s.name] = path.stat().st_mtime

        for s in loaded:
            s.loaded_at = self._loaded_at

        self._loaded_at = time.time()
        return len(loaded)

    def get(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill by name."""
        return self._skills.get(name)

    def hot_reload(self) -> dict[str, str]:
        """Check for modified SKILL.md files and reload them.

        Returns:
            dict of {skill_name: "reloaded" | "unchanged" | "removed"}
        """
        results = {}

        for name, skill in list(self._skills.items()):
            path = Path(skill.path)
            if not path.exists():
                del self._skills[name]
                results[name] = "removed"
                continue

            current_mtime = path.stat().st_mtime
            if name not in self._mtimes or current_mtime > self._mtimes[name]:
                try:
                    new_skill = load_skill(path)
                    new_skill.loaded_at = time.time()
                    self._skills[name] = new_skill
                    self._mtimes[name] = current_mtime
                    results[name] = "reloaded"
                except Exception:
                    results[name] = "error"
            else:
                results[name] = "unchanged"

        # Check for new skills
        existing_paths = {Path(s.path) for s in self._skills.values()}
        for md_file in self.skills_dir.rglob("SKILL.md"):
            if md_file not in existing_paths:
                try:
                    new_skill = load_skill(md_file)
                    new_skill.loaded_at = time.time()
                    self._skills[new_skill.name] = new_skill
                    self._mtimes[new_skill.name] = md_file.stat().st_mtime
                    results[new_skill.name] = "added"
                except Exception:
                    pass

        return results

    def get_tool_schemas(self, level: int = 1) -> list[dict]:
        """Get OpenAI tool schemas with progressive disclosure.

        Args:
            level: 1=summary only, 2=summary+instructions, 3=full
        """
        schemas = []
        for skill in self._skills.values():
            desc = skill.description
            if level >= 2 and skill.instructions:
                desc = f"{skill.description}\n\n{skill.instructions[:500]}"
            if level >= 3 and skill.implementation:
                desc = f"{skill.description}\n\n{skill.instructions[:1000]}"

            schemas.append({
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": f"Input for {skill.name}",
                            }
                        },
                    },
                },
            })
        return schemas

    def get_mcp_tools(self) -> list[dict]:
        """Return all skills as MCP tool definitions."""
        return [s.to_mcp_tool() for s in self._skills.values()]


# ── Global singleton ───────────────────────────────────────────

_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry(skills_dir: str = "skills") -> SkillRegistry:
    """Get or create the global skill registry."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry(skills_dir=skills_dir)
        _skill_registry.load_all()
    return _skill_registry
