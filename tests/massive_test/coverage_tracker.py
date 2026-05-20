"""
coverage_tracker.py — Markov chain edge coverage tracking (v3).

Tracks which state→transition edges have been traversed
during the Monte Carlo test sessions.

v3 changes:
- Added 3 states: lead_capture, preferences, handoff
- Added 10 new edges (29 total)
- Matches bot's real ConversationStateEnum more closely
"""

KNOWABLE_STATES = [
    "idle",
    "qualifying",
    "searching",
    "viewing_property",
    "scheduling",
    "completed",
    "faq",
    "appointments",
    "cancelling",
    "lead_capture",
    "preferences",
    "handoff",
    "exit",
]

# Known edges in the conversation graph (v3 — 29 edges)
KNOWN_EDGES = [
    # ── idle transitions ──
    ("idle", "qualifying"),            # Bot asks clarifying questions
    ("idle", "searching"),             # User gives enough info → direct search
    ("idle", "faq"),                   # User asks FAQ
    ("idle", "appointments"),          # User asks about their appointments
    # ── qualifying ──
    ("qualifying", "searching"),        # After clarification → search
    # ── searching ──
    ("searching", "viewing_property"),  # Search results → user picks one
    ("searching", "searching"),         # Refinement search (refine_search)
    ("searching", "idle"),              # Search → user leaves
    ("searching", "preferences"),       # User saves/updates preferences (NEW)
    ("searching", "faq"),               # User asks FAQ mid-search
    # ── viewing_property ──
    ("viewing_property", "scheduling"),   # Details → schedule
    ("viewing_property", "searching"),    # Details → another search
    ("viewing_property", "lead_capture"), # Bot asks for contact info (NEW)
    ("viewing_property", "handoff"),      # User requests human (NEW)
    ("viewing_property", "idle"),         # Details → user leaves
    # ── scheduling (BOOKING in bot's enum) ──
    ("scheduling", "completed"),          # Booking confirmed (NEW)
    ("scheduling", "scheduling"),         # Retry (conflict/change)
    ("scheduling", "idle"),               # User cancels booking
    # ── completed ──
    ("completed", "idle"),                # Done → back to idle (NEW)
    # ── faq ──
    ("faq", "searching"),                 # FAQ → then search
    ("faq", "idle"),                      # FAQ → user leaves
    # ── appointments ──
    ("appointments", "scheduling"),       # Appts → reschedule
    ("appointments", "cancelling"),       # Appts → cancel
    ("appointments", "searching"),        # Appts → new search (NEW)
    ("appointments", "idle"),             # Appts → user leaves
    # ── cancelling ──
    ("cancelling", "idle"),               # Cancel done → done
    # ── lead_capture (NEW) ──
    ("lead_capture", "scheduling"),       # Gave contact → schedule visit
    ("lead_capture", "idle"),             # Gave contact → user leaves
    # ── handoff (NEW) ──
    ("handoff", "exit"),                  # Handoff done → exit
    # ── preferences (NEW) ──
    ("preferences", "searching"),         # Saved prefs → search with them
    # ── exit ──
    ("idle", "exit"),                     # Cold exit (no real conversation)
    ("viewing_property", "exit"),         # Details → immediate exit
    ("scheduling", "exit"),               # After scheduling → exit
    ("faq", "exit"),                      # FAQ → exit
    ("appointments", "exit"),             # Appointments → exit
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
        lines.append(f"│ COVERAGE REPORT v3                            │")
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
