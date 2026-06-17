"""subscription_service.py — Suscripción SaaS vía MercadoPago (Fase 3).

NO confundir con ``billing_service.py``, que calcula cobranzas de alquiler
(cuotas/IPC/punitorios) de las inmobiliarias. Este módulo gestiona la
**suscripción de pago de la inmobiliaria al SaaS**: preapproval recurrente de
MercadoPago, sincronización por webhook y el gating por estado de suscripción.

Flujo elegido (suscripción sin plan asociado, redirect):
  1. ``create_preapproval`` hace POST /preapproval con ``status="pending"`` (sin
     card_token) → MercadoPago devuelve un ``init_point`` al que redirigimos al
     usuario para que cargue su tarjeta y autorice.
  2. Al autorizar/pausar/cancelar, MercadoPago manda un webhook firmado. Validamos
     la firma ``x-signature`` (HMAC-SHA256) y consultamos GET /preapproval/{id}
     para leer el estado real (nunca confiamos en el body del webhook).
  3. ``sync_from_preapproval_id`` mapea el estado MP → ``Subscription.status`` +
     ``tenants.status`` y persiste ``current_period_end``.

Todo lo que toca dinero (precio) sale de la config del servidor — el cliente
nunca elige el monto.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Subscription, Tenant
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

_MP_BASE = "https://api.mercadopago.com"
_PREAPPROVAL_URL = f"{_MP_BASE}/preapproval"

# MercadoPago preapproval status → nuestro Subscription.status.
# "pending" (creado pero aún sin autorizar) NO baja el trial: se omite.
_MP_STATUS_MAP: dict[str, str] = {
    "authorized": "active",
    "paused": "paused",
    "cancelled": "cancelled",
}


class SubscriptionConfigError(Exception):
    """MercadoPago no está configurado (token o precio ausentes)."""


class SubscriptionProviderError(Exception):
    """MercadoPago devolvió un error al crear el preapproval."""


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017


# ── Gating (lógica pura, testeable sin DB) ────────────────────────────────────

def subscription_grants_access(sub: Subscription | None, now: datetime | None = None) -> bool:
    """¿La suscripción habilita el acceso al dashboard?

    - ``active``  → siempre.
    - ``trial``   → solo si ``trial_ends_at`` está en el futuro.
    - resto (paused/cancelled/past_due/None) → bloqueado (402).
    """
    if sub is None:
        return False
    now = now or _now()
    if sub.status == "active":
        return True
    if sub.status == "trial":
        return sub.trial_ends_at is not None and sub.trial_ends_at > now
    return False


# ── Validación de firma del webhook ───────────────────────────────────────────

def verify_webhook_signature(
    x_signature: str | None,
    x_request_id: str | None,
    data_id: str | None,
    secret: str,
) -> bool:
    """Valida la firma ``x-signature`` de MercadoPago (HMAC-SHA256).

    El header ``x-signature`` viene como ``ts=<unix>,v1=<hex>``. El manifiesto a
    firmar es ``id:<data.id>;request-id:<x-request-id>;ts:<ts>;`` y se compara con
    ``v1`` usando HMAC-SHA256 con el secret de la notificación. Comparación en
    tiempo constante para no filtrar info por timing.
    """
    if not x_signature or not data_id or not secret:
        return False

    ts: str | None = None
    received_hash: str | None = None
    for part in x_signature.split(","):
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "ts":
            ts = value
        elif key == "v1":
            received_hash = value
    if not ts or not received_hash:
        return False

    manifest = f"id:{data_id};request-id:{x_request_id or ''};ts:{ts};"
    expected = hmac.new(
        secret.encode(), msg=manifest.encode(), digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_hash)


# ── Crear preapproval (suscripción) ───────────────────────────────────────────

async def create_preapproval(tenant_id: UUID, payer_email: str, plan: str = "profesional") -> str:
    """Crea un preapproval recurrente en MercadoPago y devuelve el ``init_point``.

    Persiste ``mp_preapproval_id``/``amount``/``plan`` en la fila Subscription del
    tenant. El precio sale SIEMPRE del catálogo del servidor (nunca del cliente).
    """
    from app.services.plans import CATALOG, TierName

    tier_name: TierName = plan if plan in CATALOG else "profesional"  # type: ignore[assignment]
    plan_obj = CATALOG[tier_name]
    if not plan_obj.self_serve:
        raise SubscriptionConfigError(
            f"El plan {tier_name} no es self-serve. Contactar a ventas."
        )

    settings = get_settings()
    token = settings.MERCADOPAGO_ACCESS_TOKEN
    price = plan_obj.price_ars_monthly
    if not token:
        raise SubscriptionConfigError(
            "MERCADOPAGO_ACCESS_TOKEN no configurado."
        )

    body = {
        "reason": plan_obj.display_name,
        "external_reference": str(tenant_id),
        "payer_email": payer_email,
        "back_url": f"{settings.PUBLIC_APP_URL}/checkout/success",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": price,
            "currency_id": "ARS",
        },
        "status": "pending",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _PREAPPROVAL_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except httpx.HTTPError as exc:
        logger.error("[mp] error de red creando preapproval: %s", exc)
        raise SubscriptionProviderError("No se pudo contactar a MercadoPago") from exc

    if resp.status_code >= 400:
        logger.error("[mp] preapproval falló (%s): %s", resp.status_code, resp.text)
        raise SubscriptionProviderError("MercadoPago rechazó la suscripción")

    data = resp.json()
    init_point = data.get("init_point") or data.get("sandbox_init_point")
    preapproval_id = data.get("id")
    if not init_point or not preapproval_id:
        logger.error("[mp] respuesta sin init_point/id: %s", data)
        raise SubscriptionProviderError("Respuesta inválida de MercadoPago")

    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant_id)
        )
        if sub is not None:
            sub.mp_preapproval_id = str(preapproval_id)
            sub.amount = price
            sub.plan = tier_name
            sub.currency = "ARS"
            await session.commit()
        else:
            logger.warning("[mp] tenant %s sin fila Subscription al subscribirse", tenant_id)

    return init_point


# ── Sincronización desde webhook ──────────────────────────────────────────────

async def _fetch_preapproval(preapproval_id: str) -> dict | None:
    settings = get_settings()
    token = settings.MERCADOPAGO_ACCESS_TOKEN
    if not token:
        logger.error("[mp] sin access token para consultar preapproval")
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_PREAPPROVAL_URL}/{preapproval_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.error("[mp] error consultando preapproval %s: %s", preapproval_id, exc)
        return None
    if resp.status_code >= 400:
        logger.error("[mp] GET preapproval %s falló (%s)", preapproval_id, resp.status_code)
        return None
    return resp.json()


def _parse_period_end(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # MercadoPago manda ISO 8601 (a veces con offset). fromisoformat soporta ambos.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def sync_from_preapproval_id(preapproval_id: str) -> bool:
    """Consulta el preapproval en MP y sincroniza Subscription + Tenant.

    Idempotente: aplicar el mismo estado varias veces no cambia el resultado.
    Devuelve True si encontró y actualizó la suscripción, False si no.
    """
    payload = await _fetch_preapproval(preapproval_id)
    if payload is None:
        return False

    mp_status = (payload.get("status") or "").lower()
    new_status = _MP_STATUS_MAP.get(mp_status)
    payer_id = payload.get("payer_id")
    external_ref = payload.get("external_reference")
    period_end = _parse_period_end(payload.get("next_payment_date"))

    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.mp_preapproval_id == str(preapproval_id))
        )
        # Fallback: primer webhook puede llegar antes de persistir el id → buscar por tenant.
        if sub is None and external_ref:
            try:
                tenant_uuid = UUID(str(external_ref))
            except (ValueError, TypeError):
                tenant_uuid = None
            if tenant_uuid is not None:
                sub = await session.scalar(
                    select(Subscription).where(Subscription.tenant_id == tenant_uuid)
                )
                if sub is not None:
                    sub.mp_preapproval_id = str(preapproval_id)

        if sub is None:
            logger.warning("[mp] webhook sin Subscription para preapproval %s", preapproval_id)
            return False

        if payer_id:
            sub.mp_payer_id = str(payer_id)
        if period_end is not None:
            sub.current_period_end = period_end

        # "pending" u otros estados intermedios no degradan el trial.
        if new_status is not None:
            sub.status = new_status
            tenant = await session.get(Tenant, sub.tenant_id)
            if tenant is not None and new_status == "active":
                tenant.status = "active"

        await session.commit()
    logger.info("[mp] preapproval %s sincronizado → %s", preapproval_id, new_status or mp_status)
    return True


# ── Job liviano: expirar trials vencidos ──────────────────────────────────────

async def mark_expired_trials() -> int:
    """Marca como ``past_due`` los trials cuyo ``trial_ends_at`` ya pasó.

    El gating ya bloquea por fecha en tiempo de request (``subscription_grants_access``),
    así que esto es solo para reflejar el estado en la DB / reportes. Idempotente.
    Devuelve cuántas filas cambió.
    """
    now = _now()
    changed = 0
    async with async_session_factory() as session:
        rows = await session.scalars(
            select(Subscription).where(Subscription.status == "trial")
        )
        for sub in rows:
            if sub.trial_ends_at is not None and sub.trial_ends_at <= now:
                sub.status = "past_due"
                changed += 1
        if changed:
            await session.commit()
    return changed
