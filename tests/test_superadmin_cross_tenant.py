"""Super-admin cross-tenant RLS tests (plan 04) — REQUIRES a Postgres test DB.

Prove the controlled cross-tenant escape hatch added in migration 0018:
  1. With the super-admin context ON, a session sees rows of EVERY tenant.
  2. With it OFF (normal request), org-aware isolation is unchanged — one tenant only.
  3. The ``app.is_superadmin`` GUC does NOT leak across pooled connections: a normal
     session right after a super-admin one sees only its own tenant.

Same harness shape as ``test_tenant_isolation.py``: a dedicated NON-superuser, table-owner
role so FORCE RLS binds exactly like prod, and each test drives its own event loop via
``asyncio.run`` so the suite is robust across pytest-asyncio versions. Skipped unless
``TEST_DATABASE_URL`` is set. NEVER point at prod.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import tenancy
from app.db.tenant_session import install_tenant_guc_listener

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="TEST_DATABASE_URL not set (Postgres required for RLS tests)"
)

TENANT_A = uuid4()
TENANT_B = uuid4()

_APP_ROLE = "inmueble_sa_app"
_APP_PASS = "sa_app_pass"


def _app_url():
    return make_url(TEST_DB_URL).set(username=_APP_ROLE, password=_APP_PASS)


def _admin_engine():
    return create_async_engine(TEST_DB_URL, pool_pre_ping=True, pool_reset_on_return="rollback")


def _app_engine():
    install_tenant_guc_listener()
    return create_async_engine(_app_url(), pool_pre_ping=True, pool_reset_on_return="rollback")


# Mirror of migration 0018's predicate on the standalone test table.
_GUC = "current_setting('app.current_tenant_id', true)::uuid"
_SUPERADMIN = "current_setting('app.is_superadmin', true) = 'on'"
_PREDICATE = (
    f"({_SUPERADMIN} "
    f"OR tenant_id = {_GUC} "
    f"OR tenant_id IN (SELECT id FROM sa_tenants WHERE parent_tenant_id = {_GUC}))"
)


async def _setup():
    eng = _admin_engine()
    default_id = str(tenancy.default_tenant_id())
    async with eng.begin() as conn:
        await conn.execute(text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_APP_ROLE}') "
            f"THEN CREATE ROLE {_APP_ROLE}; END IF; END $$;"
        ))
        await conn.execute(text(
            f"ALTER ROLE {_APP_ROLE} WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{_APP_PASS}'"
        ))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS sa_tenants ("
            " id uuid PRIMARY KEY, parent_tenant_id uuid)"
        ))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS sa_props ("
            " id serial PRIMARY KEY,"
            f" tenant_id uuid NOT NULL DEFAULT '{default_id}'::uuid REFERENCES sa_tenants(id),"
            " title text)"
        ))
        await conn.execute(text("TRUNCATE sa_props"))
        await conn.execute(text("DELETE FROM sa_tenants"))
        await conn.execute(
            text("INSERT INTO sa_tenants (id) VALUES (:a),(:b),(:d) ON CONFLICT DO NOTHING"),
            {"a": str(TENANT_A), "b": str(TENANT_B), "d": default_id},
        )
        await conn.execute(text(f"ALTER TABLE sa_props OWNER TO {_APP_ROLE}"))
        await conn.execute(text(f"ALTER TABLE sa_tenants OWNER TO {_APP_ROLE}"))
        await conn.execute(text("ALTER TABLE sa_props ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text("ALTER TABLE sa_props FORCE ROW LEVEL SECURITY"))
        await conn.execute(text("DROP POLICY IF EXISTS sa_iso ON sa_props"))
        await conn.execute(text(
            f"CREATE POLICY sa_iso ON sa_props USING {_PREDICATE} WITH CHECK {_PREDICATE}"
        ))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}"))
    sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    for tid, title in ((TENANT_A, "casa A"), (TENANT_B, "casa B")):
        async with sm() as s:
            await s.execute(text("INSERT INTO sa_props (tenant_id, title) VALUES (:t,:ti)"),
                            {"t": str(tid), "ti": title})
            await s.commit()
    await eng.dispose()


async def _teardown():
    eng = _admin_engine()
    async with eng.begin() as conn:
        await conn.execute(text(f"REVOKE ALL ON sa_props, sa_tenants FROM {_APP_ROLE}"))
        await conn.execute(text("DROP TABLE IF EXISTS sa_props"))
        await conn.execute(text("DROP TABLE IF EXISTS sa_tenants"))
    await eng.dispose()


@pytest.fixture()
def seeded():
    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


async def _titles_visible():
    """Bare query (no WHERE) — relies on RLS + the GUCs set by the listener."""
    eng = _app_engine()
    sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sm() as s:
            rows = await s.execute(text("SELECT title FROM sa_props ORDER BY title"))
            return [r[0] for r in rows]
    finally:
        await eng.dispose()


def test_superadmin_sees_all_tenants(seeded):
    """Super-admin context ON ⇒ rows of every tenant in one session."""
    async def body():
        sa_tok = tenancy.set_superadmin(True)
        tenant_tok = tenancy.set_current_tenant(TENANT_A)  # pinned tenant is irrelevant
        try:
            return await _titles_visible()
        finally:
            tenancy.reset_current_tenant(tenant_tok)
            tenancy.reset_superadmin(sa_tok)

    assert asyncio.run(body()) == ["casa A", "casa B"]


def test_normal_context_still_isolated(seeded):
    """Super-admin OFF ⇒ org-aware isolation unchanged (one tenant only)."""
    async def body(tid):
        tok = tenancy.set_current_tenant(tid)
        try:
            return await _titles_visible()
        finally:
            tenancy.reset_current_tenant(tok)

    assert asyncio.run(body(TENANT_A)) == ["casa A"]
    assert asyncio.run(body(TENANT_B)) == ["casa B"]


def test_superadmin_guc_does_not_leak(seeded):
    """A normal session right after a super-admin one sees only its own tenant."""
    async def body():
        # First, a super-admin session (sees all) on its own engine/pool.
        sa_tok = tenancy.set_superadmin(True)
        try:
            assert await _titles_visible() == ["casa A", "casa B"]
        finally:
            tenancy.reset_superadmin(sa_tok)

        # Then a normal session on a fresh pool — the listener writes is_superadmin='off'.
        tok = tenancy.set_current_tenant(TENANT_B)
        try:
            return await _titles_visible()
        finally:
            tenancy.reset_current_tenant(tok)

    assert asyncio.run(body()) == ["casa B"]
