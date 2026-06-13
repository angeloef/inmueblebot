"""Org-level routes for Enterprise multi-sucursal (the dueño's consolidated surface).

All routes require ``require_org`` (the login tenant is an Enterprise org = parent of ≥1
sucursal). They run under the ORG's RLS scope so org-aware policies expose every branch.

- ``GET  /org/branches``            list sucursales (+ manager logins, wa status)
- ``POST /org/branches``            create a sucursal (optionally with a manager login)
- ``PATCH /org/branches/{id}``      edit a sucursal
- ``POST /org/branches/{id}/manager`` create a gerente login pinned to the sucursal
- ``GET  /org/summary``             consolidated per-branch counters for the dashboard
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text

from app.api.deps import require_org
from app.core.tenancy import tenant_scope
from app.db.models import TenantAccount
from app.db.models.tenant import Tenant
from app.db.session import async_session_factory
from app.services import branch_service
from app.services.auth_service import EmailAlreadyRegistered

router = APIRouter(prefix="/org", tags=["org", "multi-sucursal"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class ManagerIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)


class BranchCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    slug: str | None = Field(default=None, max_length=60)
    timezone: str = "America/Argentina/Cordoba"
    business_hours: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=500)
    phone_number_id: str | None = Field(default=None, max_length=64)
    waba_id: str | None = Field(default=None, max_length=64)
    wa_access_token: str | None = None
    manager: ManagerIn | None = None  # opcional: crear el login del gerente en el alta


class BranchUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    business_hours: str | None = Field(default=None, max_length=300)
    timezone: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=500)
    phone_number_id: str | None = Field(default=None, max_length=64)
    waba_id: str | None = Field(default=None, max_length=64)
    wa_access_token: str | None = None


class BranchOut(BaseModel):
    id: str
    name: str
    slug: str | None
    timezone: str | None
    business_hours: str | None
    address: str | None
    wa_connected: bool
    managers: list[str]


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _managers_by_branch(branch_ids: list[UUID]) -> dict[UUID, list[str]]:
    """email list of the login accounts pinned to each branch tenant."""
    if not branch_ids:
        return {}
    async with async_session_factory() as session:
        rows = await session.execute(
            select(TenantAccount.tenant_id, TenantAccount.email).where(
                TenantAccount.tenant_id.in_(branch_ids)
            )
        )
    out: dict[UUID, list[str]] = {}
    for tid, email in rows:
        out.setdefault(tid, []).append(email)
    return out


def _branch_out(t: Tenant, managers: list[str]) -> BranchOut:
    return BranchOut(
        id=str(t.id),
        name=t.display_name,
        slug=t.slug,
        timezone=t.timezone,
        business_hours=t.business_hours,
        address=(t.branding or {}).get("address") if t.branding else None,
        wa_connected=bool(t.phone_number_id),
        managers=managers,
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/branches", response_model=list[BranchOut])
async def list_branches(account: TenantAccount = Depends(require_org)) -> list[BranchOut]:  # noqa: B008
    from app.services.tenant_service import list_branches as _list

    branches = await _list(account.tenant_id)
    managers = await _managers_by_branch([b.id for b in branches])
    return [_branch_out(b, managers.get(b.id, [])) for b in branches]


@router.post("/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
async def create_branch(
    data: BranchCreate,
    account: TenantAccount = Depends(require_org),  # noqa: B008
) -> BranchOut:
    try:
        branch = await branch_service.create_branch(
            account.tenant_id,
            display_name=data.display_name,
            slug=data.slug,
            timezone_=data.timezone,
            business_hours=data.business_hours,
            phone_number_id=data.phone_number_id,
            waba_id=data.waba_id,
            wa_access_token=data.wa_access_token,
            address=data.address,
        )
    except branch_service.PhoneNumberInUse as exc:
        raise HTTPException(status_code=409, detail="Phone number already in use") from exc
    except branch_service.BranchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    managers: list[str] = []
    if data.manager is not None:
        try:
            acct = await branch_service.create_branch_manager(
                account.tenant_id, branch.id,
                data.manager.email, data.manager.password, data.manager.full_name,
            )
            managers.append(acct.email)
        except EmailAlreadyRegistered as exc:
            raise HTTPException(status_code=409, detail="Manager email already registered") from exc
    return _branch_out(branch, managers)


@router.patch("/branches/{branch_id}", response_model=BranchOut)
async def update_branch(
    branch_id: UUID,
    data: BranchUpdate,
    account: TenantAccount = Depends(require_org),  # noqa: B008
) -> BranchOut:
    try:
        branch = await branch_service.update_branch(
            account.tenant_id, branch_id,
            display_name=data.display_name,
            business_hours=data.business_hours,
            timezone_=data.timezone,
            phone_number_id=data.phone_number_id,
            waba_id=data.waba_id,
            wa_access_token=data.wa_access_token,
            address=data.address,
        )
    except branch_service.PhoneNumberInUse as exc:
        raise HTTPException(status_code=409, detail="Phone number already in use") from exc
    except branch_service.BranchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    managers = (await _managers_by_branch([branch.id])).get(branch.id, [])
    return _branch_out(branch, managers)


@router.post("/branches/{branch_id}/manager", status_code=status.HTTP_201_CREATED)
async def create_manager(
    branch_id: UUID,
    data: ManagerIn,
    account: TenantAccount = Depends(require_org),  # noqa: B008
) -> dict:
    try:
        acct = await branch_service.create_branch_manager(
            account.tenant_id, branch_id, data.email, data.password, data.full_name,
        )
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    except branch_service.BranchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": str(acct.id), "email": acct.email, "branch_id": str(branch_id)}


@router.get("/summary")
async def consolidated_summary(account: TenantAccount = Depends(require_org)) -> dict:  # noqa: B008
    """Per-branch consolidated counters for the dueño's dashboard (basic v1).

    Loops each sucursal under ITS OWN RLS scope and counts the headline figures. Kept
    intentionally small; the Enterprise métricas item expands this into a full panel.
    """
    from app.services.tenant_service import list_branches as _list

    branches = await _list(account.tenant_id)
    per_branch: list[dict] = []
    totals = {"properties": 0, "properties_available": 0, "leads": 0,
              "visits_upcoming": 0, "charges_overdue": 0}

    for b in branches:
        counts = {"properties": 0, "properties_available": 0, "leads": 0,
                  "visits_upcoming": 0, "charges_overdue": 0}
        try:
            with tenant_scope(b.id):
                async with async_session_factory() as s:
                    counts["properties"] = await s.scalar(
                        text("SELECT count(*) FROM properties")
                    ) or 0
                    counts["properties_available"] = await s.scalar(
                        text("SELECT count(*) FROM properties WHERE status = 'available'")
                    ) or 0
                    counts["leads"] = await s.scalar(
                        text("SELECT count(*) FROM users")
                    ) or 0
                    counts["visits_upcoming"] = await s.scalar(
                        text("SELECT count(*) FROM appointments "
                             "WHERE status = 'confirmed' AND start_time >= now()")
                    ) or 0
                    counts["charges_overdue"] = await s.scalar(
                        text("SELECT count(*) FROM charges "
                             "WHERE status NOT IN ('paid','cancelled') "
                             "AND due_date < CURRENT_DATE")
                    ) or 0
        except Exception:  # a branch with missing optional tables shouldn't break the rollup
            pass
        for k in totals:
            totals[k] += counts[k]
        per_branch.append({"id": str(b.id), "name": b.display_name,
                           "wa_connected": bool(b.phone_number_id), **counts})

    return {"branches": per_branch, "totals": totals, "branch_count": len(branches)}
