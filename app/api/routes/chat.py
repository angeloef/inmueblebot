"""POST /chat — dual-router with multi-tier memory + conversation logging."""

from fastapi import APIRouter
from loguru import logger

from app.agents.schemas import ChatRequest, ChatResponse
from app.core.conversation_logger import log_turn
from app.routers.router import route_message

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Route message through S1 → S2 with multi-turn belief + cross-session memory."""
    response, belief, router_label, latency_ms = await route_message(
        message=request.message,
        session_id=request.session_id,
        phone=request.phone,
    )

    logger.debug(
        f"routed={router_label} | latency={latency_ms}ms | "
        f"turn={belief.turn_count} | criteria={belief.search_criteria_count}/4 | "
        f"confidence={response.confidence}"
    )

    # Log to conversation file for debugging
    log_turn(
        session_id=request.session_id,
        turn=belief.turn_count,
        message=request.message,
        response=response.response,
        router=router_label,
        latency_ms=latency_ms,
        confidence=response.confidence,
        tools_called=response.tools_called,
        criteria_count=belief.search_criteria_count,
        phone=request.phone,
        selection=belief.selected_property_id,
    )

    return response
