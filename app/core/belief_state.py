"""ConversationBeliefState — dynamic multi-turn state tracking (Phase 5).

Replaces rigid 15-state enum with a fluid vector of extracted criteria,
active intents, and conversation context. Evolves across turns.
"""

from dataclasses import dataclass, field
from typing import Optional


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
    last_property_data: str = ""  # Summary of last viewed property for context injection
    last_shown_detail_id: int | None = None  # Last property ID shown via get_property_details

    # ── Confirmation tracking ──────────────────────────────────
    pending_offer: Optional[str] = None  # e.g., "te paso la dirección del monoambiente"

    # ── Scheduling state ───────────────────────────────────────
    scheduling_name: str = ""
    scheduling_phone: str = ""
    scheduling_day: str = ""
    scheduling_time: str = ""
    scheduling_loop_count: int = 0  # Track repeated asks of same missing field

    turn_count: int = 0
    history: list[str] = field(default_factory=list)  # last N user messages

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
            if self.last_tool_called == "compare_properties":
                return "viewing_compare"
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
