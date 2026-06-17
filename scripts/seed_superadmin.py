"""Create-or-promote a super-admin account for the /superadmin console (plan 04).

Idempotent. Given an email + password, ensures a ``tenant_accounts`` row exists with
``role='superadmin'`` and a verified email. If the account already exists, it is promoted
(role → superadmin) and its password is (re)set. New accounts are attached to the default
tenant (super-admin is global; the FK just needs a valid tenant).

Super-admin is gated by ``require_superadmin`` (deps.py) — fail-closed — and unlocks
cross-tenant access via the ``app.is_superadmin`` GUC (migration 0018).

Run against the target DB:
    SUPERADMIN_EMAIL=dev@viviendapp.com SUPERADMIN_PASSWORD=changeme123 \
        DATABASE_URL=<...> python scripts/seed_superadmin.py

Or pass multiple as a comma-separated list in SUPERADMIN_EMAILS (shared password via
SUPERADMIN_PASSWORD) to seed both devs at once.
"""
from __future__ import annotations

import asyncio
import os
import sys

# Registers every table on Base.metadata.
import app.db.models  # noqa: F401


async def _upsert_superadmin(email: str, password: str) -> str:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.core.tenancy import default_tenant_id
    from app.db.models import TenantAccount
    from app.db.session import async_session_factory

    email = email.strip().lower()
    async with async_session_factory() as session:
        account = await session.scalar(
            select(TenantAccount).where(TenantAccount.email == email)
        )
        if account is None:
            account = TenantAccount(
                tenant_id=default_tenant_id(),
                email=email,
                full_name="Super-admin",
            )
            session.add(account)
            action = "creada"
        else:
            action = "promovida"
        account.role = "superadmin"
        account.password_hash = hash_password(password)
        # Mark the email verified so login isn't blocked by a verification gate.
        from datetime import UTC, datetime

        account.email_verified_at = account.email_verified_at or datetime.now(UTC)
        await session.commit()
    return action


async def _main() -> int:
    password = os.environ.get("SUPERADMIN_PASSWORD", "").strip()
    emails_raw = os.environ.get("SUPERADMIN_EMAILS") or os.environ.get("SUPERADMIN_EMAIL", "")
    emails = [e for e in (x.strip() for x in emails_raw.split(",")) if e]

    if not emails or not password:
        print(
            "ERROR: set SUPERADMIN_EMAIL (o SUPERADMIN_EMAILS=a,b) y SUPERADMIN_PASSWORD.",
            file=sys.stderr,
        )
        return 2
    if len(password) < 12:
        # Esta única cuenta concede acceso cross-tenant total; exigir una passphrase fuerte.
        print("ERROR: SUPERADMIN_PASSWORD debe tener al menos 12 caracteres.", file=sys.stderr)
        return 2

    for email in emails:
        action = await _upsert_superadmin(email, password)
        print(f"✓ super-admin {action}: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
