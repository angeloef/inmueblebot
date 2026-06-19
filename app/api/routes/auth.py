from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import ACCESS_COOKIE_NAME, get_current_account
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_email_token,
    create_google_signup_token,
    create_handoff_token,
    create_oauth_state_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.db.models import Subscription, Tenant, TenantAccount
from app.db.session import async_session_factory
from app.services import auth_service, email_service, google_oauth
from app.services.plans import get_plan_or_default

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie httpOnly de refresh (par de ACCESS_COOKIE_NAME). El dashboard Vite, mismo
# origen vía el proxy /api, las usa sin que el JWT toque JS.
REFRESH_COOKIE_NAME = "vivienda_refresh"

# Cookie httpOnly de corta vida que ata el state OAuth al browser (double-submit
# anti-CSRF). Solo vive durante el handshake con Google; se borra en el callback.
OAUTH_STATE_COOKIE_NAME = "vivienda_oauth_state"


# ── Request schemas ──────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    agency_name: str = Field(min_length=2, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ── Response schemas ─────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccountResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    role: str
    email_verified: bool
    avatar_color: str | None = None


class SubscriptionResponse(BaseModel):
    status: str
    plan: str | None
    tier: str | None = None
    trial_ends_at: str | None
    limits: dict | None = None
    features: list[str] | None = None
    self_serve: bool | None = None


class BranchSummary(BaseModel):
    """Una sucursal (tenant hijo) para el selector del dueño Enterprise."""
    id: str
    name: str
    slug: str | None = None
    wa_connected: bool = False


class MeResponse(BaseModel):
    account: AccountResponse
    tenant_id: str
    tenant_slug: str | None
    tenant_status: str | None
    subscription: SubscriptionResponse | None
    # True cuando el tenant ya conectó su WhatsApp (tiene phone_number_id). El
    # dashboard usa esto para mostrar el placeholder "Conectá tu WhatsApp" (Fase 4.3).
    wa_connected: bool = False
    # Métodos de login activos en la cuenta: "password" y/o "google". El dashboard lo
    # usa para sugerir agregar el método faltante (recuperación cruzada).
    auth_methods: list[str] = []
    # ── Multi-sucursal (Enterprise) ──────────────────────────────────────────
    # scope: "org" (dueño Enterprise con sucursales), "branch" (gerente de sucursal) o
    # "single" (inmobiliaria standalone / Profesional). El dashboard lo usa para mostrar el
    # selector de sucursal + la pestaña Sucursales solo a la org.
    scope: str = "single"
    plan: str | None = None                  # plan de la org (raíz de facturación)
    branches: list[BranchSummary] = []       # poblado solo para scope="org"
    # Nombre de la sucursal/org para el header (gerente: su sucursal; dueño: su org).
    org_name: str | None = None
    # 'connected' si el tenant tiene phone_number_id; 'pending' si no.
    whatsapp_status: str = "pending"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _token_response(account: TenantAccount) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(account.id, account.tenant_id, account.role),
        refresh_token=create_refresh_token(account.id, account.tenant_id, account.role),
    )


def _set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
    """Setea las cookies httpOnly de sesión para el dashboard (mismo origen vía /api).

    No rompe el flujo Next.js (BFF server-side): ese lee los tokens del body JSON;
    el Set-Cookie va al dominio de la API y el BFF lo ignora. ``Secure`` solo en
    producción para no romper el dev en http. ``SameSite=Lax`` ya protege contra
    CSRF en métodos no-seguros (no se envían cross-site).
    """
    settings = get_settings()
    secure = settings.is_production
    response.set_cookie(
        ACCESS_COOKIE_NAME, tokens.access_token,
        max_age=settings.ACCESS_TOKEN_TTL_MIN * 60,
        httponly=True, secure=secure, samesite="lax", path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME, tokens.refresh_token,
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 86400,
        httponly=True, secure=secure, samesite="lax", path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")


def _auth_methods(account: TenantAccount) -> list[str]:
    """Métodos de login activos en la cuenta (para recuperación cruzada en el front)."""
    methods: list[str] = []
    if account.password_hash:
        methods.append("password")
    if account.google_sub:
        methods.append("google")
    return methods


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def signup(req: SignupRequest, response: Response) -> TokenResponse:
    try:
        account = await auth_service.signup(req.email, req.password, req.agency_name)
    except auth_service.EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    token = create_email_token(account.id, "verify")
    await email_service.send_verification_email(account.email, token)
    tokens = _token_response(account)
    _set_auth_cookies(response, tokens)
    return tokens


@router.post("/login", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def login(req: LoginRequest, response: Response) -> TokenResponse:
    try:
        account = await auth_service.authenticate(req.email, req.password)
    except auth_service.InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc
    except auth_service.AccountSuspended as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        ) from exc
    tokens = _token_response(account)
    _set_auth_cookies(response, tokens)
    return tokens


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response) -> dict[str, bool]:
    """Cierra la sesión del dashboard borrando las cookies httpOnly."""
    _clear_auth_cookies(response)
    return {"ok": True}


@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def refresh(
    response: Response,
    req: RefreshRequest | None = None,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),  # noqa: B008
) -> TokenResponse:
    # El token llega por body (Next.js BFF) o por la cookie httpOnly (dashboard Vite).
    refresh_token = (req.refresh_token if req else None) or refresh_cookie
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token",
        )
    try:
        payload = decode_token(refresh_token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc
    # Recargar desde DB: nunca confiar en role/estado del claim. Un refresh token vive 7 días;
    # si la cuenta fue degradada o el tenant suspendido, el token viejo no debe re-emitir
    # privilegios viejos (F-01). El role y la suspensión se leen frescos de la DB.
    async with async_session_factory() as session:
        account = await session.scalar(
            select(TenantAccount).where(TenantAccount.id == account_id)
        )
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token",
            )
        tenant = await session.get(Tenant, account.tenant_id)
        if tenant is not None and tenant.status == "suspended":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended",
            )
    tokens = _token_response(account)
    _set_auth_cookies(response, tokens)
    return tokens


@router.get("/me", status_code=status.HTTP_200_OK, response_model=MeResponse)
async def me(account: TenantAccount = Depends(get_current_account)) -> MeResponse:  # noqa: B008
    _, tenant, sub = await auth_service.get_account_with_subscription(account.id)
    email_verified = account.email_verified_at is not None

    # ── Multi-sucursal scope (attrs set by get_current_account) ──────────────
    is_org = bool(getattr(account, "is_org", False))
    parent_tenant_id = getattr(account, "parent_tenant_id", None)
    billing_tenant_id = getattr(account, "billing_tenant_id", account.tenant_id)
    if is_org:
        scope = "org"
    elif parent_tenant_id is not None:
        scope = "branch"
    else:
        scope = "single"

    # La suscripción/plan SIEMPRE viven en la raíz de facturación (la org). Para un gerente
    # de sucursal hay que leer la suscripción del padre, no la de la sucursal (que no tiene).
    if billing_tenant_id != account.tenant_id:
        async with async_session_factory() as session:
            sub = await session.scalar(
                select(Subscription).where(Subscription.tenant_id == billing_tenant_id)
            )

    sub_resp: SubscriptionResponse | None = None
    plan: str | None = None
    if sub is not None:
        plan = sub.plan
        plan_obj = get_plan_or_default(sub.plan)
        sub_resp = SubscriptionResponse(
            status=sub.status,
            plan=sub.plan,
            tier=plan_obj.name,
            trial_ends_at=str(sub.trial_ends_at) if sub.trial_ends_at else None,
            limits={
                "users": plan_obj.limits.users,
                "conversations_per_month": plan_obj.limits.conversations_per_month,
                "properties": plan_obj.limits.properties,
            },
            features=sorted(plan_obj.features),
            self_serve=plan_obj.self_serve,
        )

    branches: list[BranchSummary] = []
    if is_org:
        from app.services.tenant_service import list_branches

        for b in await list_branches(account.tenant_id):
            branches.append(BranchSummary(
                id=str(b.id), name=b.display_name, slug=b.slug,
                wa_connected=bool(getattr(b, "phone_number_id", None)),
            ))

    wa_connected = bool(tenant and getattr(tenant, "phone_number_id", None))
    return MeResponse(
        account=AccountResponse(
            id=str(account.id),
            email=account.email,
            full_name=account.full_name,
            role=account.role,
            email_verified=email_verified,
            avatar_color=getattr(account, "avatar_color", None),
        ),
        tenant_id=str(account.tenant_id),
        tenant_slug=tenant.slug if tenant else None,
        tenant_status=tenant.status if tenant else None,
        subscription=sub_resp,
        wa_connected=wa_connected,
        whatsapp_status="connected" if wa_connected else "pending",
        auth_methods=_auth_methods(account),
        scope=scope,
        plan=plan,
        branches=branches,
        org_name=tenant.display_name if tenant else None,
    )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(req: ForgotPasswordRequest) -> dict[str, bool]:
    async with async_session_factory() as session:
        account = await session.scalar(
            select(TenantAccount).where(TenantAccount.email == req.email.lower())
        )
    if account is not None:
        token = create_email_token(account.id, "reset", account.token_version)
        await email_service.send_password_reset(account.email, token)
    return {"ok": True}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(req: ResetPasswordRequest) -> dict[str, bool]:
    try:
        payload = decode_token(req.token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
        ) from exc
    if payload.get("type") != "reset":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
        ) from exc
    async with async_session_factory() as session:
        account = await session.get(TenantAccount, account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
            )
        # Single-use (F-03): el token lleva el token_version con el que fue emitido. Si no
        # coincide con el actual, ya fue usado (o se emitió otro después) → rechazar. Tras
        # resetear, incrementamos para invalidar este token y cualquier otro pendiente.
        if payload.get("tv") != account.token_version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
            )
        account.password_hash = hash_password(req.new_password)
        account.token_version += 1
        await session.commit()
    return {"ok": True}


@router.get("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(token: str = Query(...)) -> dict[str, bool]:
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
        ) from exc
    if payload.get("type") != "verify":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
        ) from exc
    async with async_session_factory() as session:
        account = await session.get(TenantAccount, account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
            )
        if account.email_verified_at is None:
            account.email_verified_at = datetime.now(timezone.utc)  # noqa: UP017
            await session.commit()
    return {"verified": True}


# ── Plan 16: Perfil, contraseña, settings del tenant propio, uso ─────────────

_AVATAR_COLORS = {"navy", "teal", "violet", "green", "orange"}
_OWNER_ADMIN_ROLES = {"owner", "admin"}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    avatar_color: str | None = Field(default=None)


class UpdateMyTenantRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    business_hours: str | None = Field(default=None, max_length=300)
    timezone: str | None = Field(default=None, max_length=60)
    agent_whatsapp: str | None = Field(default=None, max_length=30)


class UsageResponse(BaseModel):
    properties: dict
    conversations_month: dict
    team_members: dict
    period_start: str | None = None
    period_end: str | None = None


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    req: ChangePasswordRequest,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict[str, bool]:
    """Cambia la contraseña de la cuenta autenticada (no reset por token)."""
    from app.core.security import verify_password

    if not account.password_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta cuenta usa Google para iniciar sesión y no tiene contraseña.",
        )
    if not verify_password(req.current_password, account.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta.",
        )
    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente a la actual.",
        )
    async with async_session_factory() as session:
        acc = await session.get(TenantAccount, account.id)
        if acc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
        acc.password_hash = hash_password(req.new_password)
        acc.token_version = (acc.token_version or 0) + 1
        await session.commit()
    return {"ok": True}


@router.patch("/profile", status_code=status.HTTP_200_OK, response_model=MeResponse)
async def update_profile(
    req: UpdateProfileRequest,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> MeResponse:
    """Actualiza nombre completo y color de avatar del perfil propio."""
    if req.avatar_color is not None and req.avatar_color not in _AVATAR_COLORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"avatar_color debe ser uno de: {', '.join(sorted(_AVATAR_COLORS))}",
        )
    async with async_session_factory() as session:
        acc = await session.get(TenantAccount, account.id)
        if acc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
        if req.full_name is not None:
            acc.full_name = req.full_name
        if req.avatar_color is not None:
            acc.avatar_color = req.avatar_color
        await session.commit()
        await session.refresh(acc)
    # Relay to the /me handler using the updated account
    return await me(acc)


class MyTenantResponse(BaseModel):
    display_name: str | None = None
    company_name: str | None = None
    business_hours: str | None = None
    timezone: str | None = None
    agent_whatsapp: str | None = None


@router.get("/my-tenant", response_model=MyTenantResponse)
async def get_my_tenant(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> MyTenantResponse:
    """Devuelve los datos editables del tenant propio (para la sección Mi inmobiliaria)."""
    from app.db.models.tenant import Tenant, TenantSettings
    from sqlalchemy import and_

    async with async_session_factory() as session:
        tenant = await session.get(Tenant, account.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")
        wa_row = await session.scalar(
            select(TenantSettings).where(
                and_(
                    TenantSettings.tenant_id == account.tenant_id,
                    TenantSettings.key == "agent_whatsapp",
                )
            )
        )
    return MyTenantResponse(
        display_name=tenant.display_name,
        company_name=getattr(tenant, "company_name", None),
        business_hours=tenant.business_hours,
        timezone=tenant.timezone,
        agent_whatsapp=wa_row.value if wa_row else None,
    )


@router.patch("/my-tenant", status_code=status.HTTP_200_OK)
async def update_my_tenant(
    req: UpdateMyTenantRequest,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict[str, bool]:
    """Self-service: el dueño/admin edita los datos de SU propia inmobiliaria."""
    from app.db.models.tenant import Tenant, TenantSettings
    from sqlalchemy import and_

    if account.role not in _OWNER_ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    updates = req.model_dump(exclude_unset=True)
    if not updates:
        return {"ok": True}

    tenant_fields = {k: v for k, v in updates.items() if k != "agent_whatsapp"}
    agent_whatsapp = updates.get("agent_whatsapp")

    async with async_session_factory() as session:
        tenant = await session.get(Tenant, account.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado")
        for key, value in tenant_fields.items():
            setattr(tenant, key, value)
        if agent_whatsapp is not None:
            row = await session.scalar(
                select(TenantSettings).where(
                    and_(
                        TenantSettings.tenant_id == account.tenant_id,
                        TenantSettings.key == "agent_whatsapp",
                    )
                )
            )
            if row is None:
                session.add(TenantSettings(
                    tenant_id=account.tenant_id,
                    key="agent_whatsapp",
                    value=agent_whatsapp,
                ))
            else:
                row.value = agent_whatsapp
        await session.commit()
    return {"ok": True}


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> UsageResponse:
    """Devuelve el uso actual del tenant vs. sus límites del plan."""
    from datetime import date, timedelta
    from sqlalchemy import func as sqlfunc
    from app.db.models.property import Property
    from app.db.models.conversation import Conversation
    from app.db.models.tenant_member import TenantMember
    from app.services.plans import get_plan_or_default

    _, tenant, sub = await auth_service.get_account_with_subscription(account.id)
    plan_name = sub.plan if sub else None
    plan_obj = get_plan_or_default(plan_name)
    limits = plan_obj.limits

    tid = account.tenant_id
    today = date.today()

    # Use billing period if available; fall back to rolling 30-day window.
    if sub and sub.current_period_end:
        period_end_date = sub.current_period_end.date()
        period_start = period_end_date - timedelta(days=30)
        period_end_str = period_end_date.isoformat()
    else:
        period_start = today - timedelta(days=30)
        period_end_str = None
    period_start_str = period_start.isoformat()

    async with async_session_factory() as session:
        prop_count = await session.scalar(
            select(sqlfunc.count()).select_from(Property).where(
                Property.tenant_id == tid,
            )
        ) or 0

        conv_count = await session.scalar(
            select(sqlfunc.count()).select_from(Conversation).where(
                Conversation.tenant_id == tid,
                Conversation.created_at >= period_start,
            )
        ) or 0

        member_count = await session.scalar(
            select(sqlfunc.count()).select_from(TenantMember).where(
                TenantMember.tenant_id == tid,
                TenantMember.status != "removed",
            )
        ) or 0
        # Count owner themselves too
        member_count += 1

    return UsageResponse(
        properties={"used": prop_count, "limit": limits.properties},
        conversations_month={"used": conv_count, "limit": limits.conversations_per_month},
        team_members={"used": member_count, "limit": limits.users},
        period_start=period_start_str,
        period_end=period_end_str,
    )


# ── Google OAuth (login/registro con Google) ──────────────────────────────────


def _safe_success_path() -> str:
    """Path relativo de redirect tras OAuth. Relativo y sin '//' → no open-redirect."""
    p = get_settings().GOOGLE_OAUTH_SUCCESS_PATH or "/"
    if not p.startswith("/") or p.startswith("//"):
        return "/"
    return p


def _safe_next_path(p: str | None) -> str:
    """Valida un deep-link como path RELATIVO del dashboard (anti open-redirect).

    Acepta solo paths que empiecen con '/' (y no '//' ni con backslash, que algunos
    browsers normalizan a '//'). Cualquier otra cosa cae al root del dashboard.
    """
    if not p or not p.startswith("/") or p.startswith("//") or "\\" in p:
        return "/"
    return p


def _landing_login_url() -> str:
    """URL del login canónico (la landing). PUBLIC_APP_URL viene de config, nunca
    de un parámetro del request → sin open-redirect."""
    return get_settings().PUBLIC_APP_URL.rstrip("/") + "/login"


def _oauth_error_redirect(reason: str = "oauth") -> RedirectResponse:
    """Vuelve al login de la landing con ?error=... (mensaje amigable, no JSON crudo)."""
    resp = RedirectResponse(
        f"{_landing_login_url()}?error={reason}", status_code=status.HTTP_303_SEE_OTHER,
    )
    resp.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    return resp


@router.get("/google/login", include_in_schema=False)
async def google_login() -> RedirectResponse:
    """Inicia el flujo OAuth: setea la cookie de state y redirige a Google."""
    if not google_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google login no está configurado",
        )
    settings = get_settings()
    state = uuid4().hex
    nonce = uuid4().hex
    state_token = create_oauth_state_token(state, nonce)
    url = google_oauth.build_authorization_url(state_token)

    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    # SameSite=lax: el callback es una navegación top-level GET desde Google, así que
    # la cookie viaja de vuelta. httpOnly: el JS nunca la ve.
    resp.set_cookie(
        OAUTH_STATE_COOKIE_NAME, state_token,
        max_age=600, httponly=True, secure=settings.is_production,
        samesite="lax", path="/",
    )
    return resp


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state_cookie: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE_NAME),  # noqa: B008
) -> RedirectResponse:
    """Callback de Google: valida state, canjea code, verifica id_token, abre sesión."""
    if not google_oauth.is_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google login no está configurado",
        )
    # El usuario canceló el consentimiento, o faltan parámetros.
    if error or not code or not state:
        return _oauth_error_redirect("oauth")

    # Double-submit anti-CSRF: el state de la query debe igualar la cookie del browser.
    if not state_cookie or state_cookie != state:
        return _oauth_error_redirect("state")
    try:
        payload = decode_token(state_cookie)
    except jwt.InvalidTokenError:
        return _oauth_error_redirect("state")
    if payload.get("type") != "oauth_state":
        return _oauth_error_redirect("state")
    nonce = payload.get("nonce", "")

    # Canje del code + verificación del id_token contra las JWKS de Google.
    try:
        raw_id_token = await google_oauth.exchange_code(code)
        claims = google_oauth.verify_id_token(raw_id_token, nonce)
    except google_oauth.GoogleOAuthError:
        return _oauth_error_redirect("oauth")

    # Login/link de cuenta EXISTENTE. Si no existe, NO se crea acá: se redirige al
    # paso de registro explícito en la landing (elegir nombre de inmobiliaria).
    try:
        account = await auth_service.login_google(claims)
    except auth_service.EmailNotVerified:
        return _oauth_error_redirect("email_unverified")
    except auth_service.AccountSuspended:
        return _oauth_error_redirect("suspended")
    except auth_service.InvalidCredentials:
        return _oauth_error_redirect("oauth")

    if account is None:
        reg_token = create_google_signup_token(
            str(claims["sub"]),
            str(claims["email"]).strip().lower(),
            (claims.get("name") or "").strip(),
        )
        base = get_settings().PUBLIC_APP_URL.rstrip("/")
        resp = RedirectResponse(
            f"{base}/signup/complete?gt={reg_token}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        resp.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
        return resp

    tokens = _token_response(account)
    resp = RedirectResponse(_safe_success_path(), status_code=status.HTTP_303_SEE_OTHER)
    _set_auth_cookies(resp, tokens)
    resp.delete_cookie(OAUTH_STATE_COOKIE_NAME, path="/")
    return resp


# ── Registro Google paso 2 (nombre de inmobiliaria) ──────────────────────────


class GoogleCompleteRequest(BaseModel):
    token: str
    agency_name: str = Field(min_length=2, max_length=200)


@router.post("/google/complete", response_model=TokenResponse)
async def google_complete(req: GoogleCompleteRequest, response: Response) -> TokenResponse:
    """Crea la cuenta Google-only con el nombre de inmobiliaria elegido.

    El token es el registration token firmado que emitió el callback (identidad
    Google ya verificada). Single-use vía Redis — un replay devuelve 400.
    """
    try:
        payload = decode_token(req.token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
        ) from exc
    if payload.get("type") != "g_signup" or not payload.get("jti"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    # 900s = el TTL del token; pasado ese tiempo la key de Redis ya no hace falta.
    if not await auth_service.mark_jti_used("gsignup", payload["jti"], 900):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    try:
        account = await auth_service.complete_google_signup(
            google_sub=str(payload.get("gsub") or ""),
            email=str(payload.get("email") or ""),
            name=str(payload.get("name") or ""),
            agency_name=req.agency_name,
        )
    except auth_service.EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered",
        ) from exc
    except auth_service.InvalidCredentials as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token",
        ) from exc

    tokens = _token_response(account)
    _set_auth_cookies(response, tokens)
    return tokens


# ── Handoff de sesión landing → dashboard ─────────────────────────────────────


class HandoffCodeRequest(BaseModel):
    # Deep-link opcional dentro del dashboard (ej: "/dashboard/clientes").
    next: str | None = None


@router.post("/handoff-code")
async def handoff_code(
    req: HandoffCodeRequest | None = None,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict[str, str]:
    """Emite un código de un solo uso (60s) para abrir la sesión en el dashboard.

    Lo llama el BFF de la landing con el access token recién emitido. El browser
    luego navega a GET /auth/handoff?code=... que setea las cookies del dashboard.
    """
    next_path = _safe_next_path(req.next if req else None)
    return {"code": create_handoff_token(account.id, account.tenant_id, account.role, next_path)}


@router.get("/handoff", include_in_schema=False)
async def handoff(code: str | None = Query(default=None)) -> RedirectResponse:
    """Canjea el código de handoff: setea cookies en el origen del dashboard.

    Single-use (Redis SETNX, fail-closed) + recarga la cuenta fresca de la DB
    (estado/rol actuales, no los del claim). Cualquier fallo → login de la landing
    con ?error=handoff — nunca un loop contra el dashboard.
    """
    def _fail() -> RedirectResponse:
        return RedirectResponse(
            f"{_landing_login_url()}?error=handoff", status_code=status.HTTP_303_SEE_OTHER,
        )

    if not code:
        return _fail()
    try:
        payload = decode_token(code)
    except jwt.InvalidTokenError:
        return _fail()
    if payload.get("type") != "handoff" or not payload.get("jti"):
        return _fail()

    # Single-use: 90s > TTL del token (60s); pasado eso la key expira sola.
    if not await auth_service.mark_jti_used("handoff", payload["jti"], 90):
        return _fail()

    try:
        account_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        return _fail()

    async with async_session_factory() as session:
        account = await session.scalar(
            select(TenantAccount).where(TenantAccount.id == account_id)
        )
        if account is None:
            return _fail()
        tenant = await session.get(Tenant, account.tenant_id)
        if tenant is not None and tenant.status == "suspended":
            return _fail()

    tokens = _token_response(account)
    resp = RedirectResponse(
        _safe_next_path(payload.get("next")), status_code=status.HTTP_303_SEE_OTHER,
    )
    _set_auth_cookies(resp, tokens)
    return resp
