"""V3 engine stub (Phase 2).

Phase 3 replaces this with the schema-guided LLM pass (one structured OpenAI call
returning { belief_delta, intent, action, tool_calls, response_plan, confidence }).

The stub echoes the message with a V3 label so the adapter/routing/switch can be
proven end-to-end before any intelligence is built.
"""

from __future__ import annotations

import time
from uuid import UUID


async def run_turn(
    *,
    phone: str,
    user_message: str,
    media_url: str | None = None,
    bsuid: str | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    """Stub engine — echoes the message and returns a contract-valid dict.

    Phase 3 replaces this body with:
        1. safety gates (emergency / human-request / out-of-scope / /reset)
        2. one schema-guided LLM call (strict json_schema, gpt-5.4-mini)
        3. deterministic execution layer (tool_calls from the engine output)
        4. optional judge (confidence < τ or critical action)
    """
    start = time.perf_counter()

    preview = user_message[:80] + ("…" if len(user_message) > 80 else "")
    response_text = f"[V3 stub — tenant {tenant_id}] Recibí: {preview}"

    latency_ms = (time.perf_counter() - start) * 1000

    return {
        "response_text": response_text,
        "tools_used": [],
        "rich_content": {},
        "confidence": 1.0,
        "router_label": "v3::stub",
        "latency_ms": latency_ms,
    }
