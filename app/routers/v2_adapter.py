"""v2 Router Adapter - bridges ChatbotSerio's route_message with inmueblebot's expected format.

Used when USE_V2_ROUTER=True. Drop-in replacement for RealEstateAgent.process_turn().
"""

import json
from typing import Optional

from loguru import logger

from app.routers.router import route_message_with_persistence as route_message
from app.agents.schemas import ChatResponse


async def process_turn_v2(
    phone: str,
    user_message: str,
    media_url: Optional[str] = None,
    bsuid: Optional[str] = None,
) -> dict:
    """Process a user turn using the v2 S1+S2 router.

    Compatible with the same signature as RealEstateAgent.process_turn().

    Args:
        phone: User's WhatsApp number (used as session_id)
        user_message: Text message from the user
        media_url: URL of media attachment (unused by v2 router for now)
        bsuid: Stable Business-Scoped User ID from the webhook (Meta identity migration)

    Returns:
        dict with: response_text, tools_used, rich_content, confidence, router_label, latency_ms
    """
    # Record the session identity for this turn so persistence tools (schedule_visit)
    # key the lead by it — never by a phone the user types into the chat.
    from app.core.identity import set_current_contact
    set_current_contact(phone, bsuid)
    # Session/state namespace keyed BSUID-first (stable identity), phone as fallback.
    # This only changes the Redis working-memory / belief / specialist-state namespace
    # (all pure string-keyed by session_id). User identity and outbound sending are
    # resolved separately (via the ContextVar / phone), so they're unaffected here.
    # Caveat: if a message ever arrives without a BSUID, session_id falls back to the
    # phone for that turn (could split a session) — BSUID arrives on all message
    # webhooks since 2026-03-31, so this is rare. See AGENTS.md "Sprint 21".
    canonical_id = bsuid or phone
    try:
        response, belief, router_label, latency_ms = await route_message(
            message=user_message,
            session_id=canonical_id,
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

        # ── request_human_assistance auto-pause ─────────────────────────
        # When the bot calls request_human_assistance, auto-pause the bot
        # so the admin knows a handoff was requested and can take over.
        if "request_human_assistance" in (response.tools_called or []):
            try:
                from app.db.session import async_session_factory
                from app.services.conversation_service import upsert_conversation, toggle_bot
                async with async_session_factory() as _db:
                    _conv_id = await upsert_conversation(_db, canonical_id, phone=phone)
                    await toggle_bot(_db, _conv_id)  # Sets bot_paused=True
            except Exception as _ha_err:
                logger.warning(f"[V2] Auto-pause on handoff failed: {_ha_err}")

        # ── Build response_plan for multi-message image sending ────────────
        if images:
            _plan_segments: list[dict] = []

            # If details were also fetched, include them first from the
            # agentic loop's intermediate MessageChunks. The LLM's final
            # response may only mention photos — we recover the details
            # text from the tool result stored in messages.
            if "get_property_details" in (response.tools_called or []):
                _details_text = _extract_detail_chunk(response)
                if _details_text:
                    _plan_segments.append({"type": "text", "content": _details_text})

            # Intro text: friendly opener + photo context
            intro = _build_photo_intro(image_title, len(images), response_text)
            _plan_segments.append({"type": "text", "content": intro})
            # Images: no caption — clean photos
            _plan_segments.append({"type": "images", "images": images[:4], "caption": ""})
            # Follow-up CTA
            follow_up = (
                "¿Tenés alguna consulta? ¿O te gustaría coordinar una visita "
                "para verlo en persona?"
            )
            _plan_segments.append({"type": "text", "content": follow_up})

            result["rich_content"]["response_plan"] = _plan_segments
            # Suppress response_text only for pure photo requests
            # (multi-tool: details were added to response_plan above)
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


def _extract_detail_chunk(response) -> str:
    """Extract property details text from the agentic loop's MessageChunks.

    When the LLM calls get_property_details then get_property_images in one
    turn, the intermediate tool results are stored in response.messages as
    MessageChunk objects. We recover the details text from the chunk whose
    tool_used field is 'get_property_details'.
    """
    if not response.messages:
        return ""
    for chunk in response.messages:
        if getattr(chunk, "tool_used", "") == "get_property_details":
            return getattr(chunk, "text", "")
    return ""


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
