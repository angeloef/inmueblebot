"""ConversationBeliefState — dynamic multi-turn state tracking (Phase 5).

Replaces rigid 15-state enum with a fluid vector of extracted criteria,
active intents, and conversation context. Evolves across turns.
"""

from dataclasses import dataclass, field
from typing import Optional


# ⏱️ Inactivity threshold: if more than this many seconds have passed since
# the last turn, the session is considered stale.
# Kept as module-level constant for backward compatibility with router imports.
# Actual value now comes from get_settings().SESSION_INACTIVITY_TIMEOUT (12 hours).
SESSION_INACTIVITY_TIMEOUT = 43200  # 12 hours — kept for import compatibility


@dataclass
class ConversationBeliefState:
    """Accumulated conversation state across multiple turns.

    Updated each turn via the state_transitioner. Guards check what
    actions are valid based on current belief.
    """

    session_id: str = ""

    # ── Search criteria (extracted from conversation) ──────────
    operation: Optional[str] = None  # "alquiler" | "venta"
    property_type: Optional[str] = None  # "departamento" | "casa" | "ph" | "terreno"
    zone: Optional[str] = None  # "Centro" | "UNAM" | "Barrio Schuster" | "Ruta 14"
    budget_max: Optional[float] = None
    bedrooms_min: Optional[int] = None

    # ── Conversation state ─────────────────────────────────────
    selected_property_id: Optional[int] = None
    active_intents: set[str] = field(default_factory=set)
    last_tool_called: Optional[str] = None
    last_search_count: int = 0
    last_search_ids: list[int] = field(default_factory=list)  # IDs from last search
    last_search_context: str = ""  # "[1] Depto Centro | [2] Casa Schuster" — for LLM ref resolution
    search_history: list[dict] = field(default_factory=list)  # last 3 searches for cross-turn disambiguation
    last_property_data: str = ""  # Summary of last viewed property for context injection
    tool_call_log: list[dict] = field(default_factory=list)  # rolling log of tool calls this session
    last_shown_detail_id: int | None = None  # Last property ID shown via get_property_details
    viewed_properties: list[dict] = field(default_factory=list)  # [{id, tipo, titulo}] seen via get_property_details
    disambiguation_candidates: list[int] = field(default_factory=list)  # candidate IDs for "¿cuál?" disambiguation
    criteria_any: set[str] = field(default_factory=set)  # criteria the user explicitly said "don't care about"
    # e.g. {"zone"} when user says "cualquier zona", {"bedrooms_min"} when "no importa los dormitorios"

    # ── Confirmation tracking ──────────────────────────────────
    pending_offer: Optional[str] = None  # e.g., "te paso la dirección del monoambiente"

    # ── Scheduling state ───────────────────────────────────────
    scheduling_name: str = ""
    scheduling_phone: str = ""
    scheduling_day: str = ""
    scheduling_time: str = ""
    scheduling_loop_count: int = 0  # Track repeated asks of same missing field
    pending_scheduling: bool = False  # True while a scheduling flow is in progress (FSM-managed)

    # ── Conversation-flow tracking (schema v4) ─────────────────
    awaiting: Optional[str] = None  # slot bot is waiting for: "scheduling_name" | "scheduling_day" | "scheduling_time" | "scheduling_confirm"
    last_bot_message: str = ""  # full text of the last bot response (for re-anchoring + LLM context)
    consecutive_failures: int = 0  # consecutive turns where the bot could not help

    turn_count: int = 0
    history: list[str] = field(default_factory=list)  # last N user messages

    # ⏱️ Timestamp (epoch seconds) of the most recent user message.
    # Used to detect stale sessions and auto-reset.
    last_updated_at: float = 0.0

    # Schema version — bump when belief structure changes to aid migration.
    schema_version: int = 4

    # ── Computed ───────────────────────────────────────────────

    @property
    def search_criteria_count(self) -> int:
        """How many search criteria are filled in (operation, type, zone, budget)."""
        return sum(
            1
            for v in [
                self.operation,
                self.property_type,
                self.zone,
                self.budget_max,
            ]
            if v is not None
        )

    @property
    def search_criteria(self) -> dict:
        """Non-None search criteria as a dict for context building."""
        criteria: dict = {}
        if self.operation:
            criteria["operación"] = self.operation
        if self.property_type:
            criteria["tipo"] = self.property_type
        if self.zone:
            criteria["zona"] = self.zone
        if self.budget_max is not None:
            criteria["presupuesto_máx"] = f"${self.budget_max:,.0f}"
        if self.bedrooms_min is not None:
            criteria["dormitorios_mín"] = self.bedrooms_min
        return criteria

    @property
    def has_selection(self) -> bool:
        """User has selected/clicked a specific property."""
        return self.selected_property_id is not None

    @property
    def scheduling_fields_filled(self) -> int:
        """How many scheduling fields are filled (name, phone, day, time)."""
        return sum(1 for v in [self.scheduling_name, self.scheduling_phone, self.scheduling_day, self.scheduling_time] if v)

    @property
    def is_first_turn(self) -> bool:
        return self.turn_count <= 1

    @property
    def state_label(self) -> str:
        """Backward-compatible state label for v1.x admin dashboard.

        Maps the fluid belief state to the old ConversationStateEnum labels
        so GET /admin/conversation/{phone}/state keeps working.
        """
        if "handoff" in self.active_intents or "human_assistance" in self.active_intents:
            return "handoff"
        if "scheduling" in self.active_intents:
            return "booking"
        if self.selected_property_id is not None:
            if self.last_tool_called == "get_property_details":
                return "viewing_detail"
            if self.last_tool_called == "get_property_images":
                return "viewing_photos"
            return "viewing_property"
        if self.search_criteria_count >= 1 or self.last_search_count > 0:
            return "searching"
        if self.search_criteria_count == 0 and self.turn_count > 0:
            return "qualifying"
        return "idle"

    def to_summary(self) -> str:
        """Human-readable summary for debugging / context injection."""
        parts = [f"Sesión {self.session_id} | Turno {self.turn_count}"]

        if self.search_criteria:
            criteria_str = ", ".join(f"{k}={v}" for k, v in self.search_criteria.items())
            parts.append(f"Criterios: {criteria_str}")

        if self.active_intents:
            parts.append(f"Intents: {', '.join(sorted(self.active_intents))}")

        if self.selected_property_id:
            parts.append(f"Propiedad seleccionada: ID {self.selected_property_id}")

        if self.last_tool_called:
            parts.append(f"Última herramienta: {self.last_tool_called}")

        return " | ".join(parts)


# ── Session store (in-memory; Phase 7 moves to Redis) ──────────

_session_store: dict[str, ConversationBeliefState] = {}


def get_belief(session_id: str) -> ConversationBeliefState:
    """Get or create a belief state for a session."""
    if session_id not in _session_store:
        _session_store[session_id] = ConversationBeliefState(session_id=session_id)
    return _session_store[session_id]


def save_belief(belief: ConversationBeliefState) -> None:
    """Persist belief state to the store."""
    _session_store[belief.session_id] = belief


def clear_session(session_id: str) -> None:
    """Remove a session from the store."""
    _session_store.pop(session_id, None)


def soft_reset(belief: ConversationBeliefState) -> ConversationBeliefState:
    """Reset volatile fields while preserving durable search context.

    Volatile (cleared): active_intents, pending_offer, scheduling_name/phone/day/time,
    scheduling_loop_count, last_tool_called.

    Durable (kept): operation, property_type, zone, budget_max, bedrooms_min,
    selected_property_id, search_history, history, turn_count.
    """
    belief.active_intents = set()
    belief.pending_offer = None
    belief.scheduling_name = ""
    belief.scheduling_phone = ""
    belief.scheduling_day = ""
    belief.scheduling_time = ""
    belief.scheduling_loop_count = 0
    belief.pending_scheduling = False
    belief.last_tool_called = None
    belief.awaiting = None
    belief.last_bot_message = ""
    belief.consecutive_failures = 0
    return belief


def is_session_stale(belief: ConversationBeliefState) -> bool:
    """Return True if the session has been inactive longer than the timeout.

    A session is stale when:
    1. It has accumulated data (turn_count > 0), AND
    2. last_updated_at > 0 (timestamp was set), AND
    3. More than SESSION_INACTIVITY_TIMEOUT seconds have passed since the last message.

    NOTE: last_updated_at == 0.0 means the timestamp was never set (new session or
    pre-timestamp migration). This is treated as NOT stale — only expire sessions where
    we actually know when they were last active.
    """
    if belief.turn_count == 0:
        return False
    # Treat 0.0 as unknown timestamp — do not treat as stale
    if belief.last_updated_at <= 0:
        return False
    import time
    from app.core.config import get_settings
    timeout = get_settings().SESSION_INACTIVITY_TIMEOUT
    elapsed = time.time() - belief.last_updated_at
    return elapsed >= timeout
