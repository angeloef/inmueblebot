"""Seed a TEST Enterprise org with 3 sucursales for manual multi-sucursal testing.

Creates (idempotent — re-run safe):
  - 1 Enterprise org (parent tenant) + active subscription (plan="Enterprise") + owner login
  - 3 sucursales (child tenants), each with a fake unique phone_number_id + a manager login
  - a few sample properties per sucursal (so the consolidated dashboard shows real numbers)

Writes credentials to ``TEST_USERS.md`` at the repo root.

Run (after migration 0013 is applied):
    python scripts/seed_enterprise_test.py

Requires DATABASE_URL (the app's normal env). Does NOT touch the existing "obera" tenant.
"""
from __future__ import annotations

import asyncio
import random
from pathlib import Path
from uuid import uuid4

# Registers every table on Base.metadata + lets us use the app's services/session.
import app.db.models  # noqa: F401


# ── Fixed test credentials (easy to type) ────────────────────────────────────
OWNER = {"email": "enterprise@test.com", "password": "enterprise123", "name": "Dueño Enterprise"}
ORG_NAME = "Inmobiliaria Enterprise (test)"
BRANCHES = [
    {"name": "Sucursal Centro", "address": "Av. San Martín 100, Centro",
     "hours": "Lun a Vie 9 a 18hs", "phone_number_id": "ENT-TEST-CENTRO-0001",
     "manager": {"email": "centro@test.com", "password": "sucursal123", "name": "Gerente Centro"}},
    {"name": "Sucursal Norte", "address": "Av. Libertad 2500, Barrio Norte",
     "hours": "Lun a Vie 9 a 18hs, Sáb 9 a 13hs", "phone_number_id": "ENT-TEST-NORTE-0002",
     "manager": {"email": "norte@test.com", "password": "sucursal123", "name": "Gerente Norte"}},
    {"name": "Sucursal Sur", "address": "Calle Brasil 800, Barrio Sur",
     "hours": "Lun a Vie 10 a 19hs", "phone_number_id": "ENT-TEST-SUR-0003",
     "manager": {"email": "sur@test.com", "password": "sucursal123", "name": "Gerente Sur"}},
]


async def _existing_account(email: str):
    from sqlalchemy import select
    from app.db.models import TenantAccount
    from app.db.session import async_session_factory

    async with async_session_factory() as s:
        return await s.scalar(select(TenantAccount).where(TenantAccount.email == email.lower()))


async def _create_org() -> object:
    """Create org parent tenant + subscription + owner account. Returns the org Tenant."""
    from datetime import datetime, timedelta, timezone
    from app.core.security import hash_password
    from app.db.models import Subscription, Tenant, TenantAccount
    from app.db.session import async_session_factory

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    async with async_session_factory() as s:
        org = Tenant(id=org_id, slug=f"enterprise-test-{org_id.hex[:6]}",
                     display_name=ORG_NAME, company_name=ORG_NAME, status="active")
        s.add(org)
        await s.flush()
        s.add(Subscription(id=uuid4(), tenant_id=org_id, provider="mercadopago",
                           status="active", plan="Enterprise", currency="ARS",
                           current_period_end=now + timedelta(days=365)))
        s.add(TenantAccount(id=uuid4(), tenant_id=org_id, email=OWNER["email"].lower(),
                            password_hash=hash_password(OWNER["password"]),
                            full_name=OWNER["name"], role="owner",
                            email_verified_at=now))
        await s.commit()
        await s.refresh(org)
        return org


async def _seed_branch_properties(branch_id) -> int:
    """Insert a handful of available properties under the branch's RLS scope."""
    from app.core.tenancy import tenant_scope
    from app.db.models.property import Property
    from app.db.session import async_session_factory

    n = random.randint(3, 6)
    created = 0
    with tenant_scope(branch_id):
        async with async_session_factory() as s:
            for _ in range(n):
                pid = random.randint(700_000_000, 799_999_999)
                op = random.choice(["alquiler", "venta"])
                s.add(Property(
                    id=pid, tenant_id=branch_id,
                    title=f"{'Departamento' if random.random() < 0.6 else 'Casa'} {random.randint(1,4)} amb.",
                    description="Propiedad de prueba (seed Enterprise).",
                    price=random.randint(80_000, 300_000) if op == "alquiler" else random.randint(40_000_000, 200_000_000),
                    currency="ARS", type=op, location="Dirección de prueba",
                    bedrooms=random.randint(1, 4), bathrooms=random.randint(1, 3),
                    area_m2=random.randint(40, 200), status="available",
                    category=random.choice(["departamento", "casa", "ph"]),
                ))
                created += 1
            await s.commit()
    return created


async def main() -> None:
    from app.services import branch_service

    existing = await _existing_account(OWNER["email"])
    if existing is not None:
        print(f"⚠️  Ya existe la cuenta {OWNER['email']} (org_id={existing.tenant_id}). "
              "Nada que hacer — el seed es idempotente.")
        _write_credentials_md(str(existing.tenant_id))
        return

    org = await _create_org()
    print(f"✅ Org Enterprise creada: {org.display_name} (id={org.id})")

    for spec in BRANCHES:
        branch = await branch_service.create_branch(
            org.id,
            display_name=spec["name"],
            business_hours=spec["hours"],
            phone_number_id=spec["phone_number_id"],
            address=spec["address"],
        )
        await branch_service.create_branch_manager(
            org.id, branch.id,
            spec["manager"]["email"], spec["manager"]["password"], spec["manager"]["name"],
        )
        count = await _seed_branch_properties(branch.id)
        print(f"   ↳ {spec['name']}: login {spec['manager']['email']} + {count} propiedades")

    _write_credentials_md(str(org.id))
    print("\n✅ Listo. Credenciales en TEST_USERS.md")


def _write_credentials_md(org_id: str) -> None:
    lines = [
        "# Usuarios de prueba — Enterprise multi-sucursal",
        "",
        "Generado por `scripts/seed_enterprise_test.py`. Para test manual del plan Enterprise.",
        "La inmobiliaria **obera** sigue intacta como Profesional (sin features de sucursal).",
        "",
        f"**Org Enterprise** (tenant padre): `{org_id}` — plan Enterprise.",
        "",
        "## Dueño (vista consolidada + entrar a cada sucursal)",
        "",
        "| Rol | Email | Contraseña |",
        "|-----|-------|------------|",
        f"| Dueño / Org | `{OWNER['email']}` | `{OWNER['password']}` |",
        "",
        "## Gerentes de sucursal (ven solo su sucursal)",
        "",
        "| Sucursal | Email | Contraseña |",
        "|----------|-------|------------|",
    ]
    for spec in BRANCHES:
        m = spec["manager"]
        lines.append(f"| {spec['name']} | `{m['email']}` | `{m['password']}` |")
    lines += [
        "",
        "> Los `phone_number_id` de cada sucursal son ficticios (no rutean WhatsApp real).",
        "> Para probar el bot por sucursal hay que cargar números Meta reales desde el dashboard.",
        "",
    ]
    path = Path(__file__).resolve().parent.parent / "TEST_USERS.md"
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
