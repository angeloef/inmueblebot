"""
v2 Router Adapter — bridges ChatbotSerio's route_message with inmueblebot's expected format.

Used when USE_V2_ROUTER=True. Drop-in replacement for RealEstateAgent.process_turn().
"""

from typing import Optional
from loguru import logger

from app.routers.router import route_message
from app.agents.schemas import ChatResponse


async def process_turn_v2(
    phone: str,
    user_message: str,
    media_url: Optional[str] = None,
) -> dict:
    """Process a user turn using the v2 S1+S2 router.

    Compatible with the same signature as RealEstateAgent.process_turn().

    Args:
        phone: User's WhatsApp number (used as session_id)
        user_message: Text message from the user
        media_url: URL of media attachment (unused by v2 router for now)

    Returns:
        dict with: response_text, tools_used, rich_content, confidence, router_label, latency_ms
    """
    try:
        response, belief, router_label, latency_ms = await route_message(
            message=user_message,
            session_id=phone,
            phone=phone,
        )

        result: dict = {
            "response_text": response.response,
            "tools_used": response.tools_called or [],
            "rich_content": {
                "images": [],
                "caption": "",
                "selected_property_id": belief.selected_property_id,
                "search_criteria": belief.search_criteria,
                "active_intents": list(belief.active_intents),
            },
            "confidence": response.confidence,
            "router_label": router_label,
            "latency_ms": latency_ms,
        }

        # Pass through any messages from the agentic loop
        if response.messages:
            result["messages"] = response.messages

        logger.debug(
            f"[V2] routed={router_label} | latency={latency_ms:.0f}ms | "
            f"turn={belief.turn_count} | confidence={response.confidence:.2f} | "
            f"tools={response.tools_called}"
        )

        return result

    except Exception as e:
        logger.opt(exception=True).error("[V2] Router error: {}", str(e))
        return {
            "response_text": "Disculpá, tuve un problema técnico. ¿Podés intentar de nuevo?",
            "tools_used": [],
            "rich_content": {},
            "confidence": 0.0,
            "router_label": "v2::error",
            "latency_ms": 0,
        }
