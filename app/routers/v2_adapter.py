"""v2 Router Adapter - bridges ChatbotSerio's route_message with inmueblebot's expected format.

Used when USE_V2_ROUTER=True. Drop-in replacement for RealEstateAgent.process_turn().
"""

import json
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

        # ── Extract image URLs when get_property_images was called ──────────
        images: list[str] = []
        image_title: str = ""
        response_text = response.response

        if "get_property_images" in (response.tools_called or []):
            # The tool now returns JSON — parse it to extract public URLs.
            # The pre-LLM shortcut already extracted display_text, but images
            # need to be fetched for WhatsApp native image sending.
            images, image_title = await _resolve_images_for_belief(belief)
            # Clean up the response text: remove any raw URL lines if present
            response_text = _clean_photo_response(response_text)

        result: dict = {
            "response_text": response_text,
            "tools_used": response.tools_called or [],
            "rich_content": {
                "images": images,
                "caption": f"Fotos de '{image_title}'" if image_title else "",
                "selected_property_id": belief.selected_property_id,
                "search_criteria": belief.search_criteria,
                "active_intents": list(belief.active_intents),
            },
            "confidence": response.confidence,
            "router_label": router_label,
            "latency_ms": latency_ms,
        }

        # ── Build response_plan for multi-message image sending ────────────
        if images:
            # Intro text: friendly opener + photo context
            intro = _build_photo_intro(image_title, len(images), response_text)
            # Follow-up CTA
            follow_up = (
                "¿Tenés alguna consulta? ¿O te gustaría coordinar una visita "
                "para verlo en persona?"
            )
            result["rich_content"]["response_plan"] = [
                {"type": "text", "content": intro},
                {"type": "images", "images": images[:4], "caption": f"Fotos — {image_title}" if image_title else "Fotos de la propiedad"},
                {"type": "text", "content": follow_up},
            ]
            # Suppress response_text only when it's a short photo header
            # so the response_plan handles all content. If the LLM generated
            # a longer response (mixed content), let it flow through too.
            if len(response_text) < 200:
                result["response_text"] = ""

        # Pass through any messages from the agentic loop
        if response.messages:
            result["messages"] = response.messages

        logger.debug(
            f"[V2] routed={router_label} | latency={latency_ms:.0f}ms | "
            f"turn={belief.turn_count} | confidence={response.confidence:.2f} | "
            f"tools={response.tools_called} | images={len(images)}"
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


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _resolve_images_for_belief(belief) -> tuple[list[str], str]:
    """Query the DB for a property's images and convert to public URLs.

    Returns (image_urls, title).
    """
    prop_id = belief.selected_property_id
    if not prop_id:
        return [], ""
    try:
        from app.tools.v2.get_property_images import get_property_images
        raw = await get_property_images(property_id=prop_id)
        parsed = json.loads(raw)
        return parsed.get("images", []), parsed.get("title", "")
    except Exception:
        return [], ""


def _clean_photo_response(text: str) -> str:
    """Remove raw image URLs from the response text if present."""
    import re
    # Remove lines that are just image URLs
    text = re.sub(r'https?://[^\s]+/media/property/[^\s]+', '', text)
    # Remove bare [N] numbering lines
    text = re.sub(r'^\s*\[\d+\]\s*$', '', text, flags=re.MULTILINE)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


def _build_photo_intro(title: str, count: int, fallback: str) -> str:
    """Build the intro text that appears before the images."""
    if title:
        return (
            f"¡Claro! Estas son las fotos de '{title}' "
            f"({count} {'imagen' if count == 1 else 'imágenes'}):"
        )
    if fallback:
        return fallback
    return f"¡Claro! Estas son las fotos:"
