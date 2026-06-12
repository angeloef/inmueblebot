"""Template-ready outbound dispatch for proactive (job-driven) WhatsApp notifications.

Proactive messages — visit reminders, payment-due reminders, contract-expiry notices,
the weekly owner report, cold-lead re-engagement — are sent OUTSIDE the WhatsApp 24h
customer-service window, so Meta requires a pre-approved HSM **template**. Until a tenant
has an approved template for a given event, we must NOT free-form the message (Meta would
reject it / risk the WABA). So every dispatch goes through this single gate:

  * If the tenant has a template name configured for the event (``wa_tpl_<event>`` in
    ``tenant_settings``) AND WhatsApp is configured → send via ``send_template``.
  * Otherwise → QUEUE: create a dashboard notification so the agent sees the reminder is
    pending and can act manually, but do NOT send the WhatsApp.

This keeps the whole notification engine useful from day one (dashboard surface + audit)
while staying compliant, and flips to real sends the moment a template name is saved —
no code change. See [recommended_pricing_plans_v3.md] Profesional 🔜 items.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from loguru import logger


class EventType(str, Enum):
    """Proactive notification event types (one per Profesional 🔜 reminder)."""

    VISIT_REMINDER = "visit_reminder"
    PAYMENT_DUE = "payment_due"
    CONTRACT_EXPIRY = "contract_expiry"
    IPC_ADJUSTMENT = "ipc_adjustment"
    WEEKLY_REPORT = "weekly_report"
    COLD_LEAD = "cold_lead"


class DispatchResult(str, Enum):
    SENT = "sent"                      # WhatsApp template delivered
    QUEUED_NO_TEMPLATE = "queued"      # no approved template → dashboard-only
    SKIPPED = "skipped"               # nothing to do (e.g. no recipient phone)
    FAILED = "failed"                 # send attempted and errored


def tenant_template_setting_key(event: EventType) -> str:
    """The ``tenant_settings`` key holding the approved template name for an event."""
    return f"wa_tpl_{event.value}"


@dataclass(frozen=True)
class Dispatch:
    """One proactive notification to deliver for the CURRENT tenant context.

    ``recipient_phone`` is the end-user (client/inquilino/owner) WhatsApp number.
    ``template_components`` are the Meta template variable components, used only when a
    template is configured. ``dashboard_*`` always populate the in-app notification.
    """

    event: EventType
    recipient_phone: str | None
    dashboard_title: str
    dashboard_body: str
    wa_text: str
    template_components: list | None = None
    dashboard_type: str | None = None
    metadata: dict | None = None


async def dispatch(tenant_id: UUID, item: Dispatch) -> DispatchResult:
    """Deliver one proactive notification through the template-ready gate.

    Always records a dashboard notification (audit + manual fallback). Sends the WhatsApp
    only if the tenant has an approved template configured for the event. Never raises —
    a single bad recipient must not abort a batch job.
    """
    from app.services.notification_service import notification_service
    from app.services.tenant_service import get_tenant_setting

    # 1) Always surface in the dashboard so the reminder is visible/auditable.
    try:
        await notification_service.create(
            type=item.dashboard_type or item.event.value,
            title=item.dashboard_title,
            body=item.dashboard_body,
            phone=item.recipient_phone,
            metadata={**(item.metadata or {}), "event": item.event.value},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"[Dispatch] dashboard notification failed ({item.event.value}): {exc}")

    if not item.recipient_phone:
        return DispatchResult.SKIPPED

    # 2) Template gate: only send if an approved template name is configured.
    template_name = await get_tenant_setting(tenant_id, tenant_template_setting_key(item.event))
    if not template_name:
        logger.info(
            f"[Dispatch] {item.event.value} QUEUED (no approved template for tenant {tenant_id}) "
            f"→ dashboard only, phone={item.recipient_phone}"
        )
        return DispatchResult.QUEUED_NO_TEMPLATE

    # 3) Send the approved template.
    try:
        from app.integrations.whatsapp import WhatsAppClient

        client = WhatsAppClient()
        if not client.is_configured:
            logger.warning(f"[Dispatch] {item.event.value}: WhatsApp not configured → QUEUED")
            return DispatchResult.QUEUED_NO_TEMPLATE
        result = await client.send_template(
            to=item.recipient_phone,
            template_name=template_name,
            components=item.template_components,
        )
        if result and not result.get("error"):
            return DispatchResult.SENT
        logger.error(f"[Dispatch] {item.event.value} template send failed: {result}")
        return DispatchResult.FAILED
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[Dispatch] {item.event.value} send raised: {exc}")
        return DispatchResult.FAILED
