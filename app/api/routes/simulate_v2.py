"""Simulate endpoint — test the chatbot without WhatsApp (Phase 11)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.schemas import ChatResponse
from app.routers.router import route_message

router = APIRouter()


class SimulateRequest(BaseModel):
    message: str
    session_id: str = "sim-default"
    phone: str = "549-test"


@router.post("/simulate", response_model=ChatResponse)
async def simulate_chat(request: SimulateRequest):
    """Simulate a WhatsApp message — test the chatbot directly.

    No WhatsApp webhook needed. Just POST a message and get the response.
    """
    response, belief, router_label, latency_ms = await route_message(
        message=request.message,
        session_id=request.session_id,
        phone=request.phone,
    )
    return response


@router.post("/simulate/multi")
async def simulate_multi(request: SimulateRequest):
    """Simulate with extra metadata — returns belief state + trace."""

    response, belief, router_label, latency_ms = await route_message(
        message=request.message,
        session_id=request.session_id,
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
