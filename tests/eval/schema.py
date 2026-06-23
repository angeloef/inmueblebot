"""Case schema + loader for the eval harness.

A *case* is a multi-turn conversation with per-turn expectations. Cases live as JSONL
under ``cases/`` split into ``dev`` (prompts may derive few-shots from these) and
``holdout`` (frozen — the real release signal; prompts must never see it).

Expectation grammar (all optional; absent = not checked):

  code grader (deterministic, from tools_used / rich_content):
    tools_any:   list[str]  — at least one of these tools ran
    tools_all:   list[str]  — all of these ran
    tools_none:  list[str]  — none of these ran
    selection:   bool       — a property got selected (rich_content.selected_property_id)
    booking:     bool       — a booking happened (schedule_visit ran)

  rule grader (regex/shape on response text):
    regex_any:   list[str]  — response matches at least one
    regex_none:  list[str]  — response matches none (anti-pattern guard)
    max_len:     int        — response length ceiling
    nonempty:    bool       — response must be non-empty

  model grader (LLM rubric, gpt-5.4-mini, advisory):
    rubric:      str        — natural-language pass criteria for the judge

  human grader:
    flag_human:  bool       — mark this turn for manual spot-check

  v4 knowledge-agent graders (deterministic assertions on rich_content):
    multi_intent_min: int   — expects ≥N sub_goals resolved (rich_content.sub_goals)
    evidence_min:     int   — expects ≥N evidence items (rich_content.evidence)
    abstain:          bool  — True=expects abstention (rich_content.abstained or confidence<0.4)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CASES_DIR = Path(__file__).parent / "cases"
VALID_SPLITS = ("dev", "holdout")


@dataclass(frozen=True)
class Expectation:
    tools_any: list[str] = field(default_factory=list)
    tools_all: list[str] = field(default_factory=list)
    tools_none: list[str] = field(default_factory=list)
    selection: bool | None = None
    booking: bool | None = None
    regex_any: list[str] = field(default_factory=list)
    regex_none: list[str] = field(default_factory=list)
    max_len: int | None = None
    nonempty: bool | None = None
    rubric: str | None = None
    flag_human: bool = False
    # v4 knowledge-agent assertions
    multi_intent_min: int | None = None
    evidence_min: int | None = None
    abstain: bool | None = None

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Expectation:
        return Expectation(
            tools_any=list(d.get("tools_any", [])),
            tools_all=list(d.get("tools_all", [])),
            tools_none=list(d.get("tools_none", [])),
            selection=d.get("selection"),
            booking=d.get("booking"),
            regex_any=list(d.get("regex_any", [])),
            regex_none=list(d.get("regex_none", [])),
            max_len=d.get("max_len"),
            nonempty=d.get("nonempty"),
            rubric=d.get("rubric"),
            flag_human=bool(d.get("flag_human", False)),
            multi_intent_min=d.get("multi_intent_min"),
            evidence_min=d.get("evidence_min"),
            abstain=d.get("abstain"),
        )


@dataclass(frozen=True)
class Turn:
    user: str
    expect: Expectation


@dataclass(frozen=True)
class Case:
    id: str
    split: str
    tags: list[str]
    description: str
    turns: list[Turn]

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Case:
        split = d.get("split", "dev")
        if split not in VALID_SPLITS:
            raise ValueError(f"case {d.get('id')!r}: invalid split {split!r}")
        turns = [
            Turn(user=t["user"], expect=Expectation.from_dict(t.get("expect", {})))
            for t in d["turns"]
        ]
        if not turns:
            raise ValueError(f"case {d.get('id')!r}: no turns")
        return Case(
            id=d["id"],
            split=split,
            tags=list(d.get("tags", [])),
            description=d.get("description", ""),
            turns=turns,
        )


def load_cases(split: str | None = None) -> list[Case]:
    """Load all cases, optionally filtered to a split. Raises on duplicate ids."""
    cases: list[Case] = []
    seen: set[str] = set()
    for path in sorted(CASES_DIR.glob("*.jsonl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = Case.from_dict(json.loads(line))
            except Exception as e:
                raise ValueError(f"{path.name}:{lineno}: {e}") from e
            if case.id in seen:
                raise ValueError(f"{path.name}:{lineno}: duplicate case id {case.id!r}")
            seen.add(case.id)
            if split is None or case.split == split:
                cases.append(case)
    return cases
