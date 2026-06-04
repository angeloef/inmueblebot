"""Cross-tenant isolation tests (V3 Phase 1) — REQUIRES a Postgres test DB.

These prove zero data leakage across tenants at three layers:
  1. App-layer scoping  (`WHERE tenant_id = resolve_tenant_id()`).
  2. The transaction-scoped GUC + Postgres RLS policy.
  3. The pooled-connection leak guard (a txn that errors must not leak its GUC to the next).

They need a REAL Postgres (RLS + set_config are Postgres-only) and are skipped unless
``TEST_DATABASE_URL`` is set. NEVER point this at prod — it creates/drops a couple of tables.
Run locally/CI with e.g.:
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/inmueblebot_test \
        pytest tests/test_tenant_isolation.py

Implementation note: deliberately NO pytest-asyncio async fixtures — each test drives its own
event loop via ``asyncio.run`` with its own engine, so the suite is robust across
pytest-asyncio versions (the project pins >=0.24, but local envs drift). The tenant ContextVar
is set on the same thread right before ``asyncio.run``, so it propagates into the coroutine.
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

# RLS is bypassed by superusers and table owners. The TEST_DATABASE_URL role is typically a
# superuser/owner (e.g. local 'postgres'), so we create a dedicated NON-superuser, NON-owner
# role and run the app-side queries as it — the realistic production condition where RLS binds.
_APP_ROLE = "inmueble_rls_app"
_APP_PASS = "rls_app_pass"


def _app_url():
    # Return the URL OBJECT — str(URL) masks the password as '***', which would break auth.
    return make_url(TEST_DB_URL).set(username=_APP_ROLE, password=_APP_PASS)


def _admin_engine():
    return create_async_engine(TEST_DB_URL, pool_pre_ping=True, pool_reset_on_return="rollback")


def _app_engine():
    install_tenant_guc_listener()
    return create_async_engine(_app_url(), pool_pre_ping=True, pool_reset_on_return="rollback")


async def _setup():
    eng = _admin_engine()
    default_id = str(tenancy.default_tenant_id())
    async with eng.begin() as conn:
        # Dedicated non-superuser app role (idempotent), password forced each run.
        await conn.execute(text(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{_APP_ROLE}') "
            f"THEN CREATE ROLE {_APP_ROLE}; END IF; END $$;"
        ))
        await conn.execute(text(
            f"ALTER ROLE {_APP_ROLE} WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{_APP_PASS}'"
        ))
        await conn.execute(text("CREATE TABLE IF NOT EXISTS t_tenants (id uuid PRIMARY KEY)"))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS t_props ("
            " id serial PRIMARY KEY,"
            f" tenant_id uuid NOT NULL DEFAULT '{default_id}'::uuid REFERENCES t_tenants(id),"
            " title text)"
        ))
        await conn.execute(text("TRUNCATE t_props"))
        await conn.execute(text("DELETE FROM t_tenants"))
        await conn.execute(
            text("INSERT INTO t_tenants (id) VALUES (:a),(:b),(:d) ON CONFLICT DO NOTHING"),
            {"a": str(TENANT_A), "b": str(TENANT_B), "d": default_id},
        )
        await conn.execute(text("ALTER TABLE t_props ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text("DROP POLICY IF EXISTS p_iso ON t_props"))
        await conn.execute(text(
            "CREATE POLICY p_iso ON t_props "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
        ))
        # Grant the app role just enough to read/write the test tables.
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}"))
        await conn.execute(text(f"GRANT SELECT, INSERT ON t_props, t_tenants TO {_APP_ROLE}"))
        await conn.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE t_props_id_seq TO {_APP_ROLE}"))
    # Seed one row per tenant as admin (RLS bypassed for setup is fine here).
    sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    for tid, title in ((TENANT_A, "casa A"), (TENANT_B, "casa B")):
        async with sm() as s:
            await s.execute(text("INSERT INTO t_props (tenant_id, title) VALUES (:t,:ti)"),
                            {"t": str(tid), "ti": title})
            await s.commit()
    await eng.dispose()


async def _teardown():
    eng = _admin_engine()
    async with eng.begin() as conn:
        await conn.execute(text(f"REVOKE ALL ON t_props, t_tenants FROM {_APP_ROLE}"))
        await conn.execute(text("DROP TABLE IF EXISTS t_props"))
        await conn.execute(text("DROP TABLE IF EXISTS t_tenants"))
    await eng.dispose()


@pytest.fixture()
def seeded():
    """Sync fixture: build + seed the standalone RLS tables, drop them after."""
    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


async def _titles_visible():
    """Bare query (no explicit WHERE) — relies on RLS + the GUC set by the listener."""
    eng = _app_engine()
    sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sm() as s:
            rows = await s.execute(text("SELECT title FROM t_props ORDER BY title"))
            return [r[0] for r in rows]
    finally:
        await eng.dispose()


def test_rls_isolates_by_guc(seeded):
    async def body(tid):
        tok = tenancy.set_current_tenant(tid)
        try:
            return await _titles_visible()
        finally:
            tenancy.reset_current_tenant(tok)

    assert asyncio.run(body(TENANT_A)) == ["casa A"]
    assert asyncio.run(body(TENANT_B)) == ["casa B"]


def test_app_layer_where_clause_isolates(seeded):
    async def body():
        eng = _app_engine()
        sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        tok = tenancy.set_current_tenant(TENANT_A)
        try:
            async with sm() as s:
                rows = await s.execute(
                    text("SELECT title FROM t_props WHERE tenant_id = :t"), {"t": str(TENANT_A)}
                )
                return [r[0] for r in rows]
        finally:
            tenancy.reset_current_tenant(tok)
            await eng.dispose()

    assert asyncio.run(body()) == ["casa A"]


def test_guc_does_not_leak_across_pooled_connections(seeded):
    """A transaction that errors must not leak its tenant GUC to the next checkout."""
    async def body():
        eng = _app_engine()
        sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        try:
            tok = tenancy.set_current_tenant(TENANT_A)
            try:
                # Any DB error mid-txn is what we want — it must abort and not leak the GUC.
                with pytest.raises(Exception):  # noqa: B017
                    async with sm() as s:
                        await s.execute(text("SELECT 1"))      # begins txn → GUC=A
                        await s.execute(text("SELECT 1/0"))    # error mid-transaction
            finally:
                tenancy.reset_current_tenant(tok)

            tok = tenancy.set_current_tenant(TENANT_B)
            try:
                async with sm() as s:
                    rows = await s.execute(text("SELECT title FROM t_props ORDER BY title"))
                    return [r[0] for r in rows]
            finally:
                tenancy.reset_current_tenant(tok)
        finally:
            await eng.dispose()

    assert asyncio.run(body()) == ["casa B"]


def test_default_fallback_when_context_unset(seeded):
    """Unset context resolves to the default tenant (V2 safety) — sees neither A nor B."""
    async def body():
        tenancy.set_current_tenant(None)
        return await _titles_visible()

    assert asyncio.run(body()) == []
