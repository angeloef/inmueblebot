from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import get_current_account
from app.core.security import (
    create_access_token,
    create_email_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.db.models import Tenant, TenantAccount
from app.db.session import async_session_factory
from app.services import auth_service, email_service

router = APIRouter(prefix="/auth", tags=["auth"])


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


class SubscriptionResponse(BaseModel):
    status: str
    plan: str | None
    trial_ends_at: str | None


class MeResponse(BaseModel):
    account: AccountResponse
    tenant_id: str
    tenant_slug: str | None
    tenant_status: str | None
    subscription: SubscriptionResponse | None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _token_response(account: TenantAccount) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(account.id, account.tenant_id, account.role),
        refresh_token=create_refresh_token(account.id, account.tenant_id, account.role),
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def signup(req: SignupRequest) -> TokenResponse:
    try:
        account = await auth_service.signup(req.email, req.password, req.agency_name)
    except auth_service.EmailAlreadyRegistered as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    token = create_email_token(account.id, "verify")
    await email_service.send_verification_email(account.email, token)
    return _token_response(account)


@router.post("/login", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
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
    return _token_response(account)


@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def refresh(req: RefreshRequest) -> TokenResponse:
    try:
        payload = decode_token(req.refresh_token)
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
    return _token_response(account)


@router.get("/me", status_code=status.HTTP_200_OK, response_model=MeResponse)
async def me(account: TenantAccount = Depends(get_current_account)) -> MeResponse:  # noqa: B008
    _, tenant, sub = await auth_service.get_account_with_subscription(account.id)
    email_verified = account.email_verified_at is not None
    sub_resp: SubscriptionResponse | None = None
    if sub is not None:
        sub_resp = SubscriptionResponse(
            status=sub.status,
            plan=sub.plan,
            trial_ends_at=str(sub.trial_ends_at) if sub.trial_ends_at else None,
        )
    return MeResponse(
        account=AccountResponse(
            id=str(account.id),
            email=account.email,
            full_name=account.full_name,
            role=account.role,
            email_verified=email_verified,
        ),
        tenant_id=str(account.tenant_id),
        tenant_slug=tenant.slug if tenant else None,
        tenant_status=tenant.status if tenant else None,
        subscription=sub_resp,
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
