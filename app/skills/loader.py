"""SKILL.md loader — parses YAML frontmatter + markdown body into SkillDefinition."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class SkillDefinition:
    """Parsed representation of a SKILL.md file."""

    name: str
    version: str
    description: str
    ttl: str = "permanent"
    category: str = "general"
    security: str = "read_only"

    # File metadata
    path: str = ""
    loaded_at: float = 0.0

    # Progressive disclosure levels
    summary: str = ""  # Level 1: always loaded
    instructions: str = ""  # Level 2: loaded when relevant
    implementation: str = ""  # Level 3: loaded on execution

    @property
    def level1_tokens(self) -> int:
        """Approximate token count for Level 1 (summary)."""
        return len(self.summary.split())

    @property
    def level2_tokens(self) -> int:
        """Approximate token count for Level 2 (instructions)."""
        return len(self.instructions.split())

    def to_mcp_tool(self) -> dict:
        """Convert to MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": f"Input for {self.name}",
                    }
                },
            },
        }


def load_skill(path: str | Path) -> SkillDefinition:
    """Parse a SKILL.md file into a SkillDefinition.

    Expected format:
    ---
    name: skill_name
    version: 1.0.0
    ...
    ---

    # Skill Title

    ## Summary
    Level 1 content

    ## Instructions
    Level 2 content

    ## Implementation
    Level 3 content
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    # Split frontmatter from body
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"No YAML frontmatter found in {path}")

    frontmatter = yaml.safe_load(parts[1])
    body = parts[2].strip()

    # Extract sections
    summary = _extract_section(body, "Summary")
    instructions = _extract_section(body, "Instructions")
    implementation = _extract_section(body, "Implementation")

    return SkillDefinition(
        name=frontmatter.get("name", path.stem),
        version=str(frontmatter.get("version", "0.1.0")),
        description=frontmatter.get("description", ""),
        ttl=frontmatter.get("ttl", "permanent"),
        category=frontmatter.get("category", "general"),
        security=frontmatter.get("security", "read_only"),
        path=str(path),
        summary=summary,
        instructions=instructions,
        implementation=implementation,
    )


def _extract_section(body: str, heading: str) -> str:
    """Extract a markdown section by ## heading name.

    Matches headings like '## Summary', '## Summary (Level 1)', etc.
    """
    pattern = rf"##\s+{re.escape(heading)}[^\n]*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def load_all_skills(skills_dir: str | Path) -> list[SkillDefinition]:
    """Load all SKILL.md files from a directory tree."""
    skills_dir = Path(skills_dir)
    skills = []

    for md_file in sorted(skills_dir.rglob("SKILL.md")):
        try:
            skill = load_skill(md_file)
            skills.append(skill)
        except Exception:
            continue

    return skills
