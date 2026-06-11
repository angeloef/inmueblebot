from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.api.deps import get_current_account
from app.api.routes.auth import (
    TokenResponse,
    _set_auth_cookies,
    _token_response,
)
from app.db.models import TenantAccount
from app.services import team_service

router = APIRouter(prefix="/team", tags=["team"])

_ADMIN_ROLES = ("owner", "admin", "superadmin")


def _require_admin(account: TenantAccount) -> None:
    if account.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


class InviteMemberIn(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, min_length=1, max_length=200)


class AcceptInviteIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class TeamMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str | None
    is_admin: bool
    status: str
    avatar_color: str | None = None
    photo_url: HttpUrl | None = None
    created_at: str

    @classmethod
    def from_member(cls, m: object) -> "TeamMemberOut":
        return cls(
            id=str(m.id),
            email=m.email,
            name=m.name,
            is_admin=m.is_admin,
            status=m.status,
            avatar_color=m.avatar_color,
            photo_url=m.photo_url,
            created_at=str(m.created_at),
        )


class InviteInfoOut(BaseModel):
    valid: bool
    email: str | None = None
    agency_name: str | None = None


@router.get("/members", response_model=list[TeamMemberOut])
async def list_members(
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> list[TeamMemberOut]:
    _require_admin(account)
    members = await team_service.list_members(account.tenant_id)
    return [TeamMemberOut.from_member(m) for m in members]


@router.post("/members", status_code=status.HTTP_201_CREATED, response_model=TeamMemberOut)
async def invite_member(
    req: InviteMemberIn,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> TeamMemberOut:
    _require_admin(account)
    try:
        member = await team_service.invite_member(
            account.tenant_id, account.id, req.email, req.name,
        )
    except team_service.EmailAlreadyHasAccount:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este email ya tiene una cuenta en ViviendApp.",
        )
    except team_service.AlreadyInvited:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este email ya fue invitado.",
        )
    return TeamMemberOut.from_member(member)


@router.delete("/members/{member_id}", status_code=status.HTTP_200_OK)
async def remove_member(
    member_id: UUID,
    account: TenantAccount = Depends(get_current_account),  # noqa: B008
) -> dict[str, bool]:
    _require_admin(account)
    try:
        await team_service.remove_member(account.tenant_id, member_id, account.id)
    except team_service.MemberNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    except team_service.CannotRemoveSelf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No podés eliminarte a vos mismo del equipo.",
        )
    except team_service.CannotRemoveOwner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar al dueño de la cuenta.",
        )
    return {"ok": True}


@router.get("/invite/{token}", response_model=InviteInfoOut)
async def invite_info(token: str) -> InviteInfoOut:
    info = await team_service.get_invite_info(token)
    if info is None:
        return InviteInfoOut(valid=False)
    email, agency_name = info
    return InviteInfoOut(valid=True, email=email, agency_name=agency_name)


@router.post(
    "/invite/{token}/accept",
    status_code=status.HTTP_200_OK,
    response_model=TokenResponse,
)
async def accept_invite(token: str, req: AcceptInviteIn, response: Response) -> TokenResponse:
    try:
        acc = await team_service.accept_invite_password(token, req.name, req.password)
    except team_service.InviteNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitación inválida",
        )
    except team_service.InviteExpired:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="La invitación expiró",
        )
    except team_service.EmailAlreadyHasAccount:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Este email ya tiene una cuenta",
        )
    tokens = _token_response(acc)
    _set_auth_cookies(response, tokens)
    return tokens
