"""V3 BeliefStateV5 — subclass of ConversationBeliefState with engine-tracking fields.

v5 adds four engine-only fields (schema_version=5, action_history, last_action,
last_intent) on top of the v4 base. These fields are NOT serialized by
app/memory/working.py (which only handles v4), so this module owns the full
serialize/deserialize cycle for v5 beliefs.

Storage key is IDENTICAL to v4 (tenant_redis_key("working", session_id)) so:
  - Tenant switching from V2→V3 reads the existing session seamlessly.
  - The v4 dashboard loader uses .get() on all fields and won't break on the
    extra v5 keys it doesn't know about.

TENANT SAFETY: The engine MUST call set_current_tenant(tenant_id) before any
Redis operation so tenant_redis_key() resolves the correct prefix. This module
never calls set_current_tenant itself — that is the engine's responsibility.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from app.core.belief_state import ConversationBeliefState
from app.core.config import get_settings
from app.routers.v3.schema import BeliefDelta


# ── V5 subclass ──────────────────────────────────────────────────────────────

@dataclass
class BeliefStateV5(ConversationBeliefState):
    """ConversationBeliefState extended with V3 engine-tracking fields.

    All v4 fields are inherited unchanged. V5 adds:
      schema_version  — overrides base default of 4 → 5
      action_history  — ordered list of action strings this session
      last_action     — most recent action taken
      last_intent     — most recent intent classified
    """

    # Override base schema_version default
    schema_version: int = 5

    # V3 engine-tracking fields (all have defaults → backward-compatible)
    action_history: list[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_intent: Optional[str] = None

    # Bedroom range support (#25): bedrooms_min is inherited; these add the upper
    # bound + match mode so a refinement re-search preserves "2 a 3 dormitorios".
    bedrooms_max: Optional[int] = None
    bedrooms_match: Optional[str] = None  # "exact" | "at_least" | "range"


# ── Delta application ────────────────────────────────────────────────────────

def apply_belief_delta(belief: BeliefStateV5, delta: BeliefDelta) -> BeliefStateV5:
    """Apply non-null fields from delta onto belief. Engine is AUTHORITATIVE.

    For each field in the delta, if the engine emitted a non-None value it
    overwrites the stored belief. Null in delta means "not mentioned this turn"
    — we never clear a stored criterion on null.
    """
    if delta.operation is not None:
        belief.operation = delta.operation
    if delta.property_type is not None:
        belief.property_type = delta.property_type
    if delta.zone is not None:
        belief.zone = delta.zone
    if delta.budget_max is not None:
        belief.budget_max = delta.budget_max
    if delta.bedrooms_min is not None:
        belief.bedrooms_min = delta.bedrooms_min
    if delta.bedrooms_max is not None:
        belief.bedrooms_max = delta.bedrooms_max
    if delta.bedrooms_match is not None:
        belief.bedrooms_match = delta.bedrooms_match
    return belief


# ── Serialization ────────────────────────────────────────────────────────────

def serialize_v5(belief: BeliefStateV5) -> str:
    """Serialize a BeliefStateV5 to JSON for Redis storage.

    Starts from all v4 fields (matching working._serialize_belief key list)
    and appends the four v5-specific keys + schema_version=5.
    """
    settings = get_settings()
    data = {
        # ── v4 fields (mirror working._serialize_belief exactly) ──────────
        "session_id": belief.session_id,
        "operation": belief.operation,
        "property_type": belief.property_type,
        "zone": belief.zone,
        "budget_max": belief.budget_max,
        "bedrooms_min": belief.bedrooms_min,
        "selected_property_id": belief.selected_property_id,
        "active_intents": list(belief.active_intents),
        "last_tool_called": belief.last_tool_called,
        "last_search_count": belief.last_search_count,
        "last_search_ids": belief.last_search_ids,
        "last_search_context": belief.last_search_context,
        "search_history": belief.search_history[-3:],
        "last_property_data": belief.last_property_data,
        "last_shown_detail_id": belief.last_shown_detail_id,
        "viewed_properties": belief.viewed_properties[-10:],
        "disambiguation_candidates": belief.disambiguation_candidates,
        "criteria_any": list(belief.criteria_any) if belief.criteria_any else [],
        "pending_offer": belief.pending_offer,
        "scheduling_name": belief.scheduling_name,
        "scheduling_phone": belief.scheduling_phone,
        "scheduling_day": belief.scheduling_day,
        "scheduling_time": belief.scheduling_time,
        "scheduling_loop_count": belief.scheduling_loop_count,
        "pending_scheduling": belief.pending_scheduling,
        "awaiting": belief.awaiting,
        "last_bot_message": belief.last_bot_message,
        "consecutive_failures": belief.consecutive_failures,
        "turn_count": belief.turn_count,
        "history": belief.history[-settings.HISTORY_WINDOW:],
        "last_updated_at": belief.last_updated_at,
        "tool_call_log": belief.tool_call_log[-settings.TOOL_LOG_MAX_ENTRIES:]
        if hasattr(settings, "TOOL_LOG_MAX_ENTRIES")
        else belief.tool_call_log[-20:],
        # ── v5 fields ────────────────────────────────────────────────────
        "schema_version": 5,
        "action_history": belief.action_history,
        "last_action": belief.last_action,
        "last_intent": belief.last_intent,
        "bedrooms_max": belief.bedrooms_max,
        "bedrooms_match": belief.bedrooms_match,
    }
    return json.dumps(data, ensure_ascii=False)


def deserialize_v5(data: str | bytes, session_id: str) -> BeliefStateV5:
    """Deserialize JSON (from Redis) into a BeliefStateV5.

    Copies all v4 fields from the dict (same field map as working._deserialize_belief)
    then reads v5 keys with .get() + defaults so old v4 data is safe.
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    d = json.loads(data)

    belief = BeliefStateV5(
        # ── v4 fields ────────────────────────────────────────────────────
        session_id=session_id,
        operation=d.get("operation"),
        property_type=d.get("property_type"),
        zone=d.get("zone"),
        budget_max=d.get("budget_max"),
        bedrooms_min=d.get("bedrooms_min"),
        selected_property_id=d.get("selected_property_id"),
        active_intents=set(d.get("active_intents", [])),
        last_tool_called=d.get("last_tool_called"),
        last_search_count=d.get("last_search_count", 0),
        last_search_ids=d.get("last_search_ids", []),
        last_search_context=d.get("last_search_context", ""),
        search_history=d.get("search_history", []),
        last_property_data=d.get("last_property_data", ""),
        last_shown_detail_id=d.get("last_shown_detail_id"),
        viewed_properties=d.get("viewed_properties", []),
        disambiguation_candidates=d.get("disambiguation_candidates", []),
        criteria_any=set(d.get("criteria_any", [])),
        pending_offer=d.get("pending_offer"),
        scheduling_name=d.get("scheduling_name", ""),
        scheduling_phone=d.get("scheduling_phone", ""),
        scheduling_day=d.get("scheduling_day", ""),
        scheduling_time=d.get("scheduling_time", ""),
        scheduling_loop_count=d.get("scheduling_loop_count", 0),
        pending_scheduling=d.get("pending_scheduling", False),
        awaiting=d.get("awaiting"),
        last_bot_message=d.get("last_bot_message", ""),
        consecutive_failures=d.get("consecutive_failures", 0),
        turn_count=d.get("turn_count", 0),
        history=d.get("history", []),
        last_updated_at=d.get("last_updated_at", 0.0),
        tool_call_log=d.get("tool_call_log", []),
        # ── v5 fields ────────────────────────────────────────────────────
        schema_version=5,
        action_history=d.get("action_history", []),
        last_action=d.get("last_action"),
        last_intent=d.get("last_intent"),
        bedrooms_max=d.get("bedrooms_max"),
        bedrooms_match=d.get("bedrooms_match"),
    )
    return belief


def migrate_v4_to_v5(belief: ConversationBeliefState | None, session_id: str) -> BeliefStateV5:
    """Promote a v4 belief (or None = fresh) to BeliefStateV5.

    Copies every v4 field; initialises the four v5 fields with defaults.
    """
    if belief is None:
        return BeliefStateV5(session_id=session_id)

    return BeliefStateV5(
        # Copy every v4 field
        session_id=belief.session_id,
        operation=belief.operation,
        property_type=belief.property_type,
        zone=belief.zone,
        budget_max=belief.budget_max,
        bedrooms_min=belief.bedrooms_min,
        selected_property_id=belief.selected_property_id,
        active_intents=set(belief.active_intents),
        last_tool_called=belief.last_tool_called,
        last_search_count=belief.last_search_count,
        last_search_ids=list(belief.last_search_ids),
        last_search_context=belief.last_search_context,
        search_history=list(belief.search_history),
        last_property_data=belief.last_property_data,
        last_shown_detail_id=belief.last_shown_detail_id,
        viewed_properties=list(belief.viewed_properties),
        disambiguation_candidates=list(belief.disambiguation_candidates),
        criteria_any=set(belief.criteria_any) if belief.criteria_any else set(),
        pending_offer=belief.pending_offer,
        scheduling_name=belief.scheduling_name,
        scheduling_phone=belief.scheduling_phone,
        scheduling_day=belief.scheduling_day,
        scheduling_time=belief.scheduling_time,
        scheduling_loop_count=belief.scheduling_loop_count,
        pending_scheduling=getattr(belief, "pending_scheduling", False),
        awaiting=belief.awaiting,
        last_bot_message=belief.last_bot_message,
        consecutive_failures=belief.consecutive_failures,
        turn_count=belief.turn_count,
        history=list(belief.history),
        last_updated_at=belief.last_updated_at,
        tool_call_log=list(belief.tool_call_log),
        # V5 defaults
        schema_version=5,
        action_history=[],
        last_action=None,
        last_intent=None,
        bedrooms_max=getattr(belief, "bedrooms_max", None),
        bedrooms_match=getattr(belief, "bedrooms_match", None),
    )


# ── Redis helpers ─────────────────────────────────────────────────────────────

async def _get_redis():
    """Reuse working.py's Redis accessor (MemoryManager pool)."""
    from app.memory.working import _get_redis as _wm_get_redis
    return await _wm_get_redis()


async def load_belief_v5(session_id: str) -> BeliefStateV5:
    """Load belief from Redis, migrating v4→v5 transparently.

    Caller MUST have called set_current_tenant(tenant_id) before this so
    tenant_redis_key() resolves the correct prefix.

    Returns a fresh BeliefStateV5 on any failure (Redis down, parse error, etc.).
    """
    from app.core.tenancy import tenant_redis_key

    key = tenant_redis_key("working", session_id)
    try:
        redis = await _get_redis()
        if redis:
            # try/finally so the connection is always returned even if get() raises
            # (plan #18): aclose() used to run only on the happy path → leak per error.
            try:
                raw = await redis.get(key)
            finally:
                await redis.aclose()
            if raw:
                try:
                    d = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                    if d.get("schema_version", 4) >= 5:
                        return deserialize_v5(raw, session_id)
                    # v4 data — build via v4 deserializer then migrate
                    from app.memory.working import _deserialize_belief
                    v4 = _deserialize_belief(raw, session_id)
                    return migrate_v4_to_v5(v4, session_id)
                except Exception as exc:
                    # A parse/migration failure here silently dropped the whole
                    # conversation (plan #15) — surface it so a corrupted belief is
                    # visible instead of presenting as a mysterious fresh start.
                    logger.warning(
                        "[V3] belief deserialize/migrate failed for {} — starting fresh: {}",
                        session_id, str(exc),
                    )
        else:
            # Redis unavailable — try v4 working_memory loader
            from app.memory.working import load_working_memory
            v4 = await load_working_memory(session_id)
            return migrate_v4_to_v5(v4, session_id)
    except Exception as exc:
        logger.warning("[V3] load_belief_v5 failed for {} — starting fresh: {}", session_id, str(exc))

    return BeliefStateV5(session_id=session_id)


async def save_belief_v5(belief: BeliefStateV5) -> None:
    """Persist a BeliefStateV5 under the same Redis key as v4.

    Caller MUST have called set_current_tenant(tenant_id) before this.
    Fails silently — a metrics/persistence failure must never break a turn.
    """
    from app.core.tenancy import tenant_redis_key

    key = tenant_redis_key("working", belief.session_id)
    settings = get_settings()
    try:
        redis = await _get_redis()
        if redis:
            # try/finally so the connection is always returned even if set() raises
            # (plan #18): aclose() used to run only on the happy path → leak per error.
            try:
                data = serialize_v5(belief)
                await redis.set(key, data, ex=settings.WORKING_MEMORY_TTL)
            finally:
                await redis.aclose()
        else:
            # Redis unavailable — fall back to in-memory store
            from app.core.belief_state import save_belief
            save_belief(belief)
    except Exception as exc:
        # A save failure means the next turn loses this turn's slots/history (plan #15).
        # Still non-fatal to the current reply, but it must be visible.
        logger.warning("[V3] save_belief_v5 failed for {}: {}", belief.session_id, str(exc))
