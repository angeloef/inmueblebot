"""Router de facturación SaaS (Fase 3 — MercadoPago).

Endpoints:
  - POST /billing/subscribe   (auth)      → crea preapproval, devuelve init_point.
  - GET  /billing/status      (auth)      → estado de la suscripción + trial.
  - POST /webhooks/mercadopago (público)  → valida firma y sincroniza estado.

Regla de dinero: el monto del plan SIEMPRE sale de la config del servidor; el
cliente no puede elegir el precio. El webhook NUNCA confía en el body — valida la
firma y vuelve a consultar el preapproval contra la API de MercadoPago.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_account
from app.core.config import get_settings
from app.core.rate_limiter import rate_limiter
from app.db.models import Subscription, TenantAccount
from app.db.session import async_session_factory
from app.services import subscription_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])

# Anti-abuse: each subscribe call opens a MercadoPago preapproval, so cap how
# often one tenant can trigger it. Generous enough for legit retries (declined
# card, abandoned checkout), tight enough to stop spam.
_SUBSCRIBE_MAX = 5
_SUBSCRIBE_WINDOW_S = 300  # 5 minutes


async def _subscribe_rate_limit(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> TenantAccount:
    """Per-tenant rate limit for subscribe (Redis-backed, degrades open)."""
    key = f"billing:subscribe:{account.tenant_id}"
    if not await rate_limiter.check_key(key, _SUBSCRIBE_MAX, _SUBSCRIBE_WINDOW_S):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de suscripción. Probá de nuevo en unos minutos.",
            headers={"Retry-After": str(_SUBSCRIBE_WINDOW_S)},
        )
    return account


# ── Response schemas ─────────────────────────────────────────────────────────


class SubscribeResponse(BaseModel):
    init_point: str


class BillingStatusResponse(BaseModel):
    status: str
    plan: str | None
    trial_ends_at: str | None
    current_period_end: str | None
    has_access: bool


# ── Endpoints autenticados ───────────────────────────────────────────────────


@router.post(
    "/billing/subscribe",
    status_code=status.HTTP_200_OK,
    response_model=SubscribeResponse,
)
async def subscribe(
    account: TenantAccount = Depends(_subscribe_rate_limit),  # noqa: B008
) -> SubscribeResponse:
    """Crea la suscripción en MercadoPago y devuelve el ``init_point`` para redirigir."""
    try:
        init_point = await subscription_service.create_preapproval(
            account.tenant_id, account.email
        )
    except subscription_service.SubscriptionConfigError as exc:
        # Falta config del servidor (token/precio). No es culpa del cliente.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pagos no disponibles temporalmente",
        ) from exc
    except subscription_service.SubscriptionProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo iniciar la suscripción",
        ) from exc
    return SubscribeResponse(init_point=init_point)


@router.get(
    "/billing/status",
    status_code=status.HTTP_200_OK,
    response_model=BillingStatusResponse,
)
async def billing_status(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> BillingStatusResponse:
    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == account.tenant_id)
        )
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription",
        )
    return BillingStatusResponse(
        status=sub.status,
        plan=sub.plan,
        trial_ends_at=str(sub.trial_ends_at) if sub.trial_ends_at else None,
        current_period_end=str(sub.current_period_end) if sub.current_period_end else None,
        has_access=subscription_service.subscription_grants_access(sub),
    )


# ── Webhook público de MercadoPago ───────────────────────────────────────────


@router.post("/webhooks/mercadopago", status_code=status.HTTP_200_OK)
async def mercadopago_webhook(request: Request) -> dict[str, bool]:
    """Recibe notificaciones de MercadoPago. Valida la firma y sincroniza estado.

    Devuelve 200 salvo firma inválida (403). Idempotente: MercadoPago reintenta y
    puede reenviar duplicados; aplicar el mismo estado no cambia nada.
    """
    settings = get_settings()
    secret = settings.MERCADOPAGO_WEBHOOK_SECRET

    # La firma de MercadoPago se calcula SOLO sobre el data.id del query param +
    # x-request-id + ts. Validamos ANTES de leer el body, para no parsear JSON de
    # un caller no autenticado (reduce superficie de DoS).
    data_id = request.query_params.get("data.id") or request.query_params.get("id")
    x_signature = request.headers.get("x-signature")
    x_request_id = request.headers.get("x-request-id")

    # ── Validación de firma (fail-closed en producción) ──────────────────────
    if secret:
        if not subscription_service.verify_webhook_signature(
            x_signature, x_request_id, data_id, secret
        ):
            logger.warning("[mp] webhook con firma inválida (data.id=%s)", data_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    elif settings.is_production:
        # Sin secret configurado en prod: no podemos validar → rechazamos.
        logger.error("[mp] MERCADOPAGO_WEBHOOK_SECRET ausente en producción — webhook rechazado")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook not configured")
    else:
        logger.warning("[mp] sin webhook secret (dev) — firma NO validada")

    # Firma OK (o dev): recién ahora leemos el body para type/fallbacks.
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not data_id and isinstance(body, dict):
        data_id = (body.get("data") or {}).get("id") or body.get("id")
    notif_type = (
        request.query_params.get("type")
        or request.query_params.get("topic")
        or (body.get("type") if isinstance(body, dict) else None)
        or (body.get("topic") if isinstance(body, dict) else None)
    )

    # Solo nos interesan las notificaciones de suscripción. El resto se acepta y se ignora.
    if (
        notif_type
        and "preapproval" not in str(notif_type).lower()
        and "subscription" not in str(notif_type).lower()
    ):
        return {"ok": True}

    if not data_id:
        logger.warning("[mp] webhook sin data.id — ignorado")
        return {"ok": True}

    await subscription_service.sync_from_preapproval_id(str(data_id))
    return {"ok": True}
