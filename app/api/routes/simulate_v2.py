"""Simulate endpoint — test the chatbot without WhatsApp (Phase 11)."""

from fastapi import APIRouter
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


@router.post("/simulate", response_model=ChatResponse)
async def simulate_chat(request: SimulateRequest):
    """Simulate a WhatsApp message — test the chatbot directly.

    No WhatsApp webhook needed. Just POST a message and get the response.
    """
    # Set the session identity ContextVar — the real webhook does this in
    # process_turn_v2; simulate calls route_message directly, so identity-keyed
    # tools (schedule_visit) would otherwise have no contact to resolve.
    set_current_contact(request.phone, request.bsuid)
    response, belief, router_label, latency_ms = await route_message(
        message=request.message,
        session_id=request.bsuid or request.session_id,
        phone=request.phone,
    )
    return response


@router.post("/simulate/multi")
async def simulate_multi(request: SimulateRequest):
    """Simulate with extra metadata — returns belief state + trace."""

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
    }
