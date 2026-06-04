"""Simulate endpoint — test the chatbot without WhatsApp.

Phase 0b: added `router` + `tenant` + `reset` so the eval harness can replay cases
**through the adapter path** (`process_turn_v2`) — the same code the webhook runs —
instead of calling `route_message` directly (which bypassed pause/auto-pause/rich_content).

- `router=None`  → legacy direct `route_message` (back-compat, returns ChatResponse).
- `router="v2"`  → through `process_turn_v2` (adapter dict).
- `router="v3"`  → through `process_turn_v3` if present (Phase 2); else HTTP 501.
- `reset=True`   → clear the session's working memory first (per-case isolation).
- `tenant`       → accepted now, threaded once multi-tenancy lands (Phase 1/2); logged.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.agents.schemas import ChatResponse
from app.core.identity import set_current_contact
from app.routers.router import route_message_with_persistence as route_message

router = APIRouter()


class SimulateRequest(BaseModel):
    message: str
    session_id: str = "sim-default"
    phone: str = "549-test"
    bsuid: str | None = None  # optional — exercise the BSUID identity path
    router: Optional[str] = None  # None | "v2" | "v3" — None = legacy direct path
    tenant: Optional[str] = None  # forward-compat (Phase 1/2); logged for now
    reset: bool = False  # clear working memory before this turn (per-case isolation)


async def _maybe_reset(req: SimulateRequest) -> None:
    """Clear the session's working memory so an eval case starts clean."""
    if not req.reset:
        return
    try:
        from app.core.memory import memory_manager
        await memory_manager.reset_user_context(req.phone)
        if req.bsuid:
            await memory_manager.reset_user_context(req.bsuid)
        logger.info(f"[simulate] reset memory for {req.bsuid or req.phone}")
    except Exception as e:  # reset is best-effort
        logger.warning(f"[simulate] reset failed: {e}")


async def _run_adapter(req: SimulateRequest) -> dict[str, Any]:
    """Route through the same adapter the webhook uses."""
    if req.tenant:
        logger.info(f"[simulate] tenant={req.tenant} (no-op until multi-tenancy lands)")

    if req.router == "v2":
        from app.routers.v2_adapter import process_turn_v2
        return await process_turn_v2(
            phone=req.phone, user_message=req.message, bsuid=req.bsuid
        )

    if req.router == "v3":
        try:
            from app.routers.v3.adapter import process_turn_v3  # type: ignore
        except Exception as e:
            raise HTTPException(
                status_code=501,
                detail="router=v3 not available yet (built in Phase 2).",
            ) from e
        # V3 adds a tenant param; pass it through when present.
        return await process_turn_v3(  # type: ignore[call-arg]
            phone=req.phone, user_message=req.message, bsuid=req.bsuid, tenant=req.tenant
        )

    raise HTTPException(status_code=400, detail=f"unknown router '{req.router}'")


@router.post("/simulate", response_model=ChatResponse)
async def simulate_chat(request: SimulateRequest):
    """Simulate a WhatsApp message — direct chatbot test (legacy, returns ChatResponse).

    Kept for back-compat. For adapter-path testing (eval harness), use the
    `router=` param on `/simulate/multi`.
    """
    await _maybe_reset(request)
    # Set the session identity ContextVar — the real webhook does this in
    # process_turn_v2; the direct path needs it for identity-keyed tools.
    set_current_contact(request.phone, request.bsuid)
    response, belief, router_label, latency_ms = await route_message(
        message=request.message,
        session_id=request.bsuid or request.session_id,
        phone=request.phone,
    )
    return response


@router.post("/simulate/multi")
async def simulate_multi(request: SimulateRequest):
    """Simulate with metadata. The eval harness targets THIS endpoint.

    With `router` set, routes through the adapter (webhook-equivalent) and returns the
    adapter dict. Without it, falls back to the legacy direct trace.
    """
    await _maybe_reset(request)

    # ── Adapter path (eval harness / webhook-equivalent) ──────────────────
    if request.router:
        result = await _run_adapter(request)
        return {
            "response": result.get("response_text", ""),
            "tools_called": result.get("tools_used", []),
            "confidence": result.get("confidence"),
            "router": result.get("router_label"),
            "latency_ms": result.get("latency_ms"),
            "rich_content": result.get("rich_content", {}),
            "via": "adapter",
        }

    # ── Legacy direct path (back-compat) ──────────────────────────────────
    set_current_contact(request.phone, request.bsuid)
    response, belief, router_label, latency_ms = await route_message(
        message=request.message,
        session_id=request.bsuid or request.session_id,
        phone=request.phone,
    )
    return {
        "response": response.response,
        "tools_called": response.tools_called,
        "confidence": response.confidence,
        "router": router_label,
        "latency_ms": latency_ms,
        "turn": belief.turn_count,
        "criteria_count": belief.search_criteria_count,
        "selection": belief.selected_property_id,
        "active_intents": list(belief.active_intents),
        "via": "direct",
    }
