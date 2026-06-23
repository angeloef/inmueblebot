"""V4 Knowledge Agent Router Adapter.

Same guaranteed-dict contract as V3:
    response_text, tools_used, rich_content, confidence, router_label, latency_ms

KA0 stub: engine delegates to V3. Intelligence arrives KA1+.
"""

from __future__ import annotations

import time
from uuid import UUID

from loguru import logger


async def process_turn_v4(
    phone: str,
    user_message: str,
    media_url: str | None = None,
    bsuid: str | None = None,
    tenant: str | None = None,
) -> dict:
    """Process a user turn using the V4 router.

    Returns the guaranteed-subset dict:
        response_text, tools_used, rich_content, confidence, router_label, latency_ms
    """
    from app.core.identity import set_current_contact
    set_current_contact(phone, bsuid)

    tenant_id = _resolve_tenant(tenant)
    from app.core.tenancy import set_current_tenant
    set_current_tenant(tenant_id)

    start = time.perf_counter()
    try:
        from app.routers.v4.engine import run_turn

        result = await run_turn(
            phone=phone,
            user_message=user_message,
            media_url=media_url,
            bsuid=bsuid,
            tenant_id=tenant_id,
        )

        from app.core.turn_metrics import emit_turn_metrics
        emit_turn_metrics(
            router="v4",
            tenant_id=str(tenant_id) if tenant_id else None,
            router_label=result.get("router_label", "v4::stub"),
            tools=result.get("tools_used", []),
            latency_ms=result.get("latency_ms", 0.0),
            confidence=result.get("confidence", 1.0),
        )

        logger.debug(
            "[V4] router_label={} | latency={:.0f}ms | tenant={}",
            result.get("router_label"),
            result.get("latency_ms", 0),
            tenant_id,
        )

        await _persist_turn_v4(
            phone=phone, bsuid=bsuid, user_message=user_message, result=result,
        )
        await _handle_handoff_v4(phone=phone, bsuid=bsuid, result=result)
        return result

    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.opt(exception=True).error("[V4] Router error: {}", str(exc))
        from app.core.turn_metrics import emit_turn_metrics
        emit_turn_metrics(
            router="v4",
            tenant_id=str(tenant_id) if tenant_id else None,
            router_label="v4::error",
            latency_ms=latency_ms,
        )
        return {
            "response_text": "Disculpá, tuve un problema técnico. ¿Podés intentar de nuevo?",
            "tools_used": [],
            "rich_content": {},
            "confidence": 0.0,
            "router_label": "v4::error",
            "latency_ms": latency_ms,
        }


def _bot_text_for_persistence(result: dict) -> str:
    """Best-effort plain-text rendering of the bot's reply for inbox persistence."""
    text = (result.get("response_text") or "").strip()
    if text:
        return text
    rich = result.get("rich_content") or {}
    plan = rich.get("response_plan") if isinstance(rich, dict) else None
    if isinstance(plan, list):
        parts = [
            str(seg.get("content", "")).strip()
            for seg in plan
            if isinstance(seg, dict) and seg.get("type") == "text" and seg.get("content")
        ]
        if parts:
            return "\n\n".join(parts)
        if any(isinstance(seg, dict) and seg.get("type") == "images" for seg in plan):
            return "📷 (imágenes enviadas)"
    return ""


async def _persist_turn_v4(
    *, phone: str, bsuid: str | None, user_message: str, result: dict,
) -> None:
    """Persist a V4 turn to the inbox tables + push SSE events for the dashboard."""
    bot_text = _bot_text_for_persistence(result)
    if not bot_text:
        return
    canonical_id = bsuid or phone
    try:
        from app.db.session import async_session_factory
        from app.services.conversation_service import save_turn, upsert_conversation
        async with async_session_factory() as db:
            conv_id = await upsert_conversation(db, canonical_id, phone=phone)
            await save_turn(
                db,
                conv_id,
                user_message=user_message,
                bot_response=bot_text,
                tools_called=result.get("tools_used") or [],
                router=result.get("router_label") or "v4",
                latency_ms=result.get("latency_ms") or 0,
                confidence=result.get("confidence") or 0,
            )
    except Exception as exc:
        logger.warning("[V4] persist turn failed (non-fatal): {}", str(exc))


_HANDOFF_LABELS = frozenset({
    "v4::emergency", "v4::human-handoff", "v4::limit-daily", "v4::limit-abuse",
    # V3 labels pass through the stub during KA0
    "v3::emergency", "v3::human-handoff", "v3::limit-daily", "v3::limit-abuse",
})

_HANDOFF_REASONS: dict[str, str] = {
    "v4::emergency": "emergencia",
    "v4::limit-daily": "límite diario de mensajes alcanzado",
    "v4::limit-abuse": "mensajes fuera de tema/abusivos reiterados",
    "v4::human-handoff": "user_requested",
    "v3::emergency": "emergencia",
    "v3::limit-daily": "límite diario de mensajes alcanzado",
    "v3::limit-abuse": "mensajes fuera de tema/abusivos reiterados",
    "v3::human-handoff": "user_requested",
}


async def _handle_handoff_v4(*, phone: str, bsuid: str | None, result: dict) -> None:
    """On a V4 human handoff, create a dashboard notification and pause the bot."""
    tools = result.get("tools_used") or []
    label = result.get("router_label") or ""
    is_handoff = "request_human_assistance" in tools or label in _HANDOFF_LABELS
    if not is_handoff:
        return

    reason = _HANDOFF_REASONS.get(label, "user_requested")
    try:
        from app.services.notification_service import notification_service
        await notification_service.handoff_requested(phone=phone, reason=reason)
    except Exception as exc:
        logger.warning("[V4] handoff notification failed (non-fatal): {}", str(exc))

    canonical_id = bsuid or phone
    try:
        from app.db.session import async_session_factory
        from app.services.conversation_service import (
            is_bot_paused,
            toggle_bot,
            upsert_conversation,
        )
        async with async_session_factory() as db:
            conv_id = await upsert_conversation(db, canonical_id, phone=phone)
            if not await is_bot_paused(db, phone):
                await toggle_bot(db, conv_id)
    except Exception as exc:
        logger.warning("[V4] handoff auto-pause failed (non-fatal): {}", str(exc))


def _resolve_tenant(tenant: str | None) -> UUID | None:
    if tenant:
        try:
            return UUID(tenant)
        except ValueError:
            pass

    from app.core.tenancy import resolve_tenant_id
    return resolve_tenant_id()
