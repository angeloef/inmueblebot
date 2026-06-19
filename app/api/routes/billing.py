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

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_account
from app.core.config import get_settings
from app.core.rate_limiter import rate_limiter
from app.db.models import Subscription, TenantAccount
from app.db.session import async_session_factory
from app.services import subscription_service
from app.services.plans import CATALOG, get_plan_or_default, list_plans

logger = logging.getLogger(__name__)

_MP_BASE = "https://api.mercadopago.com"

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


class SubscribeRequest(BaseModel):
    plan: str = "profesional"


class SubscribeResponse(BaseModel):
    init_point: str


class BillingStatusResponse(BaseModel):
    status: str
    plan: str | None
    tier: str | None
    trial_ends_at: str | None
    current_period_end: str | None
    has_access: bool
    limits: dict | None = None
    features: list[str] | None = None
    self_serve: bool | None = None


class PaymentRecord(BaseModel):
    id: str
    date: str
    amount: float
    currency: str
    status: str


class PaymentsResponse(BaseModel):
    payments: list[PaymentRecord]


# ── Endpoints autenticados ───────────────────────────────────────────────────


@router.post(
    "/billing/subscribe",
    status_code=status.HTTP_200_OK,
    response_model=SubscribeResponse,
)
async def subscribe(
    body: SubscribeRequest,
    account: TenantAccount = Depends(_subscribe_rate_limit),  # noqa: B008
) -> SubscribeResponse:
    """Crea la suscripción en MercadoPago y devuelve el ``init_point`` para redirigir."""
    plan_name: str = body.plan.lower()
    if plan_name not in CATALOG:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan inválido. Opciones: {', '.join(CATALOG)}",
        )
    if not CATALOG[plan_name].self_serve:  # type: ignore[index]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "enterprise_no_self_serve",
                "message": "Enterprise no es self-serve. Contactanos para una cotización.",
            },
        )
    try:
        init_point = await subscription_service.create_preapproval(
            account.tenant_id, account.email, plan=plan_name
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
    plan_obj = get_plan_or_default(sub.plan)
    return BillingStatusResponse(
        status=sub.status,
        plan=sub.plan,
        tier=plan_obj.name,
        trial_ends_at=str(sub.trial_ends_at) if sub.trial_ends_at else None,
        current_period_end=str(sub.current_period_end) if sub.current_period_end else None,
        has_access=subscription_service.subscription_grants_access(sub),
        limits={
            "users": plan_obj.limits.users,
            "conversations_per_month": plan_obj.limits.conversations_per_month,
            "properties": plan_obj.limits.properties,
        },
        features=sorted(plan_obj.features),
        self_serve=plan_obj.self_serve,
    )


@router.get(
    "/billing/payments",
    status_code=status.HTTP_200_OK,
    response_model=PaymentsResponse,
)
async def list_payments(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> PaymentsResponse:
    """Historial de pagos del preapproval activo del tenant (tenant-scoped)."""
    async with async_session_factory() as session:
        sub = await session.scalar(
            select(Subscription).where(Subscription.tenant_id == account.tenant_id)
        )
    if sub is None or not sub.mp_preapproval_id:
        return PaymentsResponse(payments=[])

    settings = get_settings()
    token = settings.MERCADOPAGO_ACCESS_TOKEN
    if not token:
        return PaymentsResponse(payments=[])

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_MP_BASE}/authorized_payments/search",
                params={"preapproval_id": sub.mp_preapproval_id},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.error("[mp] error fetching authorized_payments: %s", exc)
        return PaymentsResponse(payments=[])

    if resp.status_code >= 400:
        logger.warning("[mp] authorized_payments search failed (%s)", resp.status_code)
        return PaymentsResponse(payments=[])

    results = (resp.json().get("results") or [])
    payments = sorted(
        [
            PaymentRecord(
                id=str(p.get("id", "")),
                date=p.get("date_approved") or p.get("date_created") or "",
                amount=float(p.get("transaction_amount") or 0),
                currency=p.get("currency_id") or "ARS",
                status=p.get("status") or "unknown",
            )
            for p in results
        ],
        key=lambda p: p.date,
        reverse=True,
    )
    return PaymentsResponse(payments=payments)


@router.get(
    "/billing/plans",
    status_code=status.HTTP_200_OK,
)
async def get_plans() -> dict:
    """Lista el catálogo de planes con precios y características. Público (no requiere auth)."""
    return {"plans": list_plans()}


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
