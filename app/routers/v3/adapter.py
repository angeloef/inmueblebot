"""V3 Router Adapter (Phase 2 skeleton).

Mirrors the return-dict **guaranteed-subset** contract of ``process_turn_v2``:

    response_text  str
    tools_used     list[str]
    rich_content   dict
    confidence     float
    router_label   str
    latency_ms     float

The signature extends v2's by adding ``tenant`` so the webhook can thread the resolved
tenant explicitly (the V2 callsite is unchanged — it has no tenant param).

Phase 3 replaces the stub engine call with the schema-guided LLM pass.
"""

from __future__ import annotations

import time
from uuid import UUID

from loguru import logger


async def process_turn_v3(
    phone: str,
    user_message: str,
    media_url: str | None = None,
    bsuid: str | None = None,
    tenant: str | None = None,  # UUID string or slug; falls back to ContextVar
) -> dict:
    """Process a user turn using the V3 router.

    Returns the same guaranteed-subset dict as ``process_turn_v2``:
        response_text, tools_used, rich_content, confidence, router_label, latency_ms

    The ``messages`` and ``rich_content.response_plan`` keys are NOT guaranteed (same
    as V2 — they appear only for multi-message turns). Contract tests assert only the
    guaranteed subset.
    """
    from app.core.identity import set_current_contact
    set_current_contact(phone, bsuid)

    tenant_id = _resolve_tenant(tenant)
    # Pin the tenant for the whole adapter scope so the persistence calls below land in
    # the same tenant the engine served (run_turn sets it too, but error paths may not).
    from app.core.tenancy import set_current_tenant
    set_current_tenant(tenant_id)

    start = time.perf_counter()
    try:
        from app.routers.v3.engine import run_turn

        result = await run_turn(
            phone=phone,
            user_message=user_message,
            media_url=media_url,
            bsuid=bsuid,
            tenant_id=tenant_id,
        )

        from app.core.turn_metrics import emit_turn_metrics
        emit_turn_metrics(
            router="v3",
            tenant_id=str(tenant_id) if tenant_id else None,
            router_label=result.get("router_label", "v3::stub"),
            tools=result.get("tools_used", []),
            latency_ms=result.get("latency_ms", 0.0),
            confidence=result.get("confidence", 1.0),
        )

        logger.debug(
            "[V3] router_label={} | latency={:.0f}ms | tenant={}",
            result.get("router_label"),
            result.get("latency_ms", 0),
            tenant_id,
        )

        # ── Inbox persistence + handoff (parity with V2) ──────────────────────
        # V3's engine only writes belief state to Redis; it never persisted the turn
        # to the inbox tables. The dashboard Chat tab, its live SSE stream, and the
        # new-lead/handoff notifications all key off conversation_service — which V2
        # reaches via route_message_with_persistence but V3 never called. That's why
        # WhatsApp turns served by V3 were invisible on the dashboard.
        await _persist_turn_v3(
            phone=phone, bsuid=bsuid, user_message=user_message, result=result,
        )
        await _handle_handoff_v3(phone=phone, bsuid=bsuid, result=result)
        return result

    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.opt(exception=True).error("[V3] Router error: {}", str(exc))
        from app.core.turn_metrics import emit_turn_metrics
        emit_turn_metrics(
            router="v3",
            tenant_id=str(tenant_id) if tenant_id else None,
            router_label="v3::error",
            latency_ms=latency_ms,
        )
        return {
            "response_text": "Disculpá, tuve un problema técnico. ¿Podés intentar de nuevo?",
            "tools_used": [],
            "rich_content": {},
            "confidence": 0.0,
            "router_label": "v3::error",
            "latency_ms": latency_ms,
        }


def _bot_text_for_persistence(result: dict) -> str:
    """Best-effort plain-text rendering of the bot's reply for the inbox record.

    response_text is empty on image / multi-segment turns (the content lives in
    rich_content.response_plan); fall back to the plan's text segments so the dashboard
    shows what the bot actually said instead of a blank bubble.
    """
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


async def _persist_turn_v3(
    *, phone: str, bsuid: str | None, user_message: str, result: dict,
) -> None:
    """Persist a V3 turn to the inbox tables + push SSE events for the dashboard.

    Mirrors V2's route_message_with_persistence. Best-effort: the user already got
    their reply, so a persistence failure must never surface as an error.
    """
    bot_text = _bot_text_for_persistence(result)
    if not bot_text:
        return
    canonical_id = bsuid or phone
    try:
        from app.db.session import async_session_factory
        from app.services.conversation_service import upsert_conversation, save_turn
        async with async_session_factory() as db:
            conv_id = await upsert_conversation(db, canonical_id, phone=phone)
            await save_turn(
                db,
                conv_id,
                user_message=user_message,
                bot_response=bot_text,
                tools_called=result.get("tools_used") or [],
                router=result.get("router_label") or "v3",
                latency_ms=result.get("latency_ms") or 0,
                confidence=result.get("confidence") or 0,
            )
    except Exception as exc:
        logger.warning("[V3] persist turn failed (non-fatal): {}", str(exc))


async def _handle_handoff_v3(*, phone: str, bsuid: str | None, result: dict) -> None:
    """On a V3 human handoff, create a dashboard notification and pause the bot.

    Fires when the turn used request_human_assistance (LLM tool path) or hit the
    emergency / human-handoff safety gate. The V2/V3 request_human_assistance tool only
    returns confirmation text — it neither notifies nor pauses — so for V3 a handoff was
    completely invisible on the dashboard. Adds the missing notification and mirrors
    v2_adapter's auto-pause. Best-effort.
    """
    tools = result.get("tools_used") or []
    label = result.get("router_label") or ""
    is_handoff = (
        "request_human_assistance" in tools
        or label in ("v3::emergency", "v3::human-handoff")
    )
    if not is_handoff:
        return

    reason = "emergencia" if label == "v3::emergency" else "user_requested"
    try:
        from app.services.notification_service import notification_service
        await notification_service.handoff_requested(phone=phone, reason=reason)
    except Exception as exc:
        logger.warning("[V3] handoff notification failed (non-fatal): {}", str(exc))

    canonical_id = bsuid or phone
    try:
        from app.db.session import async_session_factory
        from app.services.conversation_service import (
            upsert_conversation, toggle_bot, is_bot_paused,
        )
        async with async_session_factory() as db:
            conv_id = await upsert_conversation(db, canonical_id, phone=phone)
            # Guard against an unpause: toggle_bot flips the flag, so only flip when the
            # bot isn't already paused (a repeat handoff must not re-enable the bot).
            if not await is_bot_paused(db, phone):
                await toggle_bot(db, conv_id)
    except Exception as exc:
        logger.warning("[V3] handoff auto-pause failed (non-fatal): {}", str(exc))


def _resolve_tenant(tenant: str | None) -> UUID | None:
    """Resolve the effective tenant id for this turn.

    Priority:
    1. ``tenant`` param is a valid UUID string → use it directly.
    2. ContextVar is set (webhook path — already resolved in process_messages) → use it.
    3. Fallback to the default tenant (V2 safety / simulate path without tenant).
    """
    if tenant:
        try:
            return UUID(tenant)
        except ValueError:
            pass  # slug — fall through to ContextVar

    from app.core.tenancy import resolve_tenant_id
    return resolve_tenant_id()
