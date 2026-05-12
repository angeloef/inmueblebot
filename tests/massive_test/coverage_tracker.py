"""
coverage_tracker.py — Markov chain edge coverage tracking.

Tracks which state→transition edges have been traversed
during the Monte Carlo test sessions.
"""

KNOWABLE_STATES = [
    "idle",
    "qualifying",
    "searching",
    "viewing_property",
    "scheduling",
    "faq",
    "appointments",
    "cancelling",
    "exit",
]

# Known edges in the conversation graph
KNOWN_EDGES = [
    ("idle", "qualifying"),       # Bot asks clarifying questions
    ("idle", "searching"),        # User gives enough info → direct search
    ("idle", "faq"),              # User asks FAQ
    ("idle", "appointments"),     # User asks about their appointments
    ("qualifying", "searching"),  # After clarification → search
    ("searching", "viewing_property"),  # Search results → user picks one
    ("searching", "idle"),        # Search → user leaves
    ("searching", "searching"),   # Refinement search
    ("viewing_property", "scheduling"),  # Details → schedule
    ("viewing_property", "searching"),   # Details → another search
    ("viewing_property", "idle"),        # Details → user leaves
    ("scheduling", "idle"),       # Schedule done → user leaves
    ("scheduling", "scheduling"), # Schedule retry (conflict)
    ("faq", "searching"),         # FAQ → then search
    ("faq", "idle"),              # FAQ → user leaves
    ("appointments", "scheduling"),  # Appts → reschedule
    ("appointments", "cancelling"),  # Appts → cancel
    ("appointments", "idle"),        # Appts → user leaves
    ("cancelling", "idle"),      # Cancel done → done
]


class CoverageTracker:
    def __init__(self):
        self.edges_visited = set()
        self.states_visited = set()
        self.total_turns = 0
        self.sessions = 0
        self.violations = []  # (session_id, turn, rule, msg)

    def record_turn(self, from_state: str, to_state: str, session_id: int):
        """Record a state transition."""
        self.total_turns += 1
        self.states_visited.add(from_state)
        self.states_visited.add(to_state)
        edge = (from_state, to_state)
        self.edges_visited.add(edge)

    def record_violation(self, session_id: int, turn: int, rule: str, msg: str):
        self.violations.append((session_id, turn, rule, msg))

    def record_session(self):
        self.sessions += 1

    @property
    def edge_coverage(self) -> float:
        if not KNOWN_EDGES:
            return 100.0
        return len(self.edges_visited) / len(KNOWN_EDGES) * 100

    @property
    def edges_by_state(self, state: str) -> int:
        return len([(a, b) for a, b in KNOWN_EDGES if a == state and (a, b) in self.edges_visited])

    def report(self) -> str:
        lines = []
        lines.append(f"┌────────────────────────────────────────────────┐")
        lines.append(f"│ COVERAGE REPORT                                │")
        lines.append(f"├────────────────────────────────────────────────┤")
        lines.append(f"│ Sessions:      {self.sessions:>3d}                               │")
        lines.append(f"│ Total turns:   {self.total_turns:>3d}                               │")
        lines.append(f"│ Edge coverage: {self.edge_coverage:>5.1f}%  ({len(self.edges_visited)}/{len(KNOWN_EDGES)})                     │")
        lines.append(f"│ States seen:   {len(self.states_visited):>3d}/{len(KNOWABLE_STATES)}                               │")
        lines.append(f"│ Violations:    {len(self.violations):>3d}                               │")
        lines.append(f"└────────────────────────────────────────────────┘")

        # Edge detail
        lines.append(f"\n  Edges visited by state:")
        states_with_edges = {}
        for a, b in KNOWN_EDGES:
            states_with_edges.setdefault(a, []).append(b)
        for state, targets in sorted(states_with_edges.items()):
            visited = sum(1 for t in targets if (state, t) in self.edges_visited)
            total = len(targets)
            status = "✅" if visited == total else f"{visited}/{total}"
            lines.append(f"    {state:20s} → {visited}/{total} edges {status}")

        return "\n".join(lines)
