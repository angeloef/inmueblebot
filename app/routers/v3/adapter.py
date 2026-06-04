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
