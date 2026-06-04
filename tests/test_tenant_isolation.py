"""Cross-tenant isolation tests (V3 Phase 1) — REQUIRES a Postgres test DB.

These prove zero data leakage across tenants at three layers:
  1. App-layer scoping  (`WHERE tenant_id = resolve_tenant_id()`).
  2. The transaction-scoped GUC + Postgres RLS policy.
  3. The pooled-connection leak guard (a txn that errors must not leak its GUC to the next).

They need a REAL Postgres (RLS + set_config are Postgres-only) and are skipped unless
``TEST_DATABASE_URL`` is set. NEVER point this at prod — it creates/drops a couple of tables.
Run locally/CI with e.g.:
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot_test \
        pytest tests/test_tenant_isolation.py
"""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import tenancy
from app.db.tenant_session import install_tenant_guc_listener

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="TEST_DATABASE_URL not set (Postgres required for RLS tests)"
)

TENANT_A = uuid4()
TENANT_B = uuid4()


@pytest_asyncio.fixture()
async def engine():
    install_tenant_guc_listener()
    eng = create_async_engine(TEST_DB_URL, pool_pre_ping=True, pool_reset_on_return="rollback")
    async with eng.begin() as conn:
        # Minimal standalone schema for the test (tenants + a scoped table).
        await conn.execute(text("CREATE TABLE IF NOT EXISTS t_tenants (id uuid PRIMARY KEY)"))
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS t_props ("
            " id serial PRIMARY KEY,"
            " tenant_id uuid NOT NULL DEFAULT '%s'::uuid REFERENCES t_tenants(id),"
            " title text)" % str(tenancy.default_tenant_id())
        ))
        await conn.execute(text("TRUNCATE t_props"))
        await conn.execute(text("DELETE FROM t_tenants"))
        await conn.execute(text("INSERT INTO t_tenants (id) VALUES (:a),(:b)"),
                           {"a": str(TENANT_A), "b": str(TENANT_B)})
        # Enable + FORCE RLS so the policy applies regardless of connection role.
        await conn.execute(text("ALTER TABLE t_props ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text("ALTER TABLE t_props FORCE ROW LEVEL SECURITY"))
        await conn.execute(text("DROP POLICY IF EXISTS p_iso ON t_props"))
        await conn.execute(text(
            "CREATE POLICY p_iso ON t_props "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)"
        ))
    # Seed one row per tenant (app-layer: explicit tenant_id, GUC set via listener).
    sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    for tid, title in ((TENANT_A, "casa A"), (TENANT_B, "casa B")):
        tok = tenancy.set_current_tenant(tid)
        try:
            async with sm() as s:
                await s.execute(text("INSERT INTO t_props (tenant_id, title) VALUES (:t,:ti)"),
                                {"t": str(tid), "ti": title})
                await s.commit()
        finally:
            tenancy.reset_current_tenant(tok)

    yield eng, sm

    async with eng.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS t_props"))
        await conn.execute(text("DROP TABLE IF EXISTS t_tenants"))
    await eng.dispose()


async def _titles_visible(sm):
    """Bare query (no explicit WHERE) — relies on RLS + the GUC set by the listener."""
    async with sm() as s:
        rows = await s.execute(text("SELECT title FROM t_props ORDER BY title"))
        return [r[0] for r in rows]


@pytest.mark.asyncio
async def test_rls_isolates_by_guc(engine):
    _eng, sm = engine
    tok = tenancy.set_current_tenant(TENANT_A)
    try:
        assert await _titles_visible(sm) == ["casa A"]
    finally:
        tenancy.reset_current_tenant(tok)

    tok = tenancy.set_current_tenant(TENANT_B)
    try:
        assert await _titles_visible(sm) == ["casa B"]
    finally:
        tenancy.reset_current_tenant(tok)


@pytest.mark.asyncio
async def test_app_layer_where_clause_isolates(engine):
    """Even without RLS, the explicit WHERE tenant_id filter must isolate."""
    _eng, sm = engine
    tok = tenancy.set_current_tenant(TENANT_A)
    try:
        async with sm() as s:
            rows = await s.execute(
                text("SELECT title FROM t_props WHERE tenant_id = :t"), {"t": str(TENANT_A)}
            )
            assert [r[0] for r in rows] == ["casa A"]
    finally:
        tenancy.reset_current_tenant(tok)


@pytest.mark.asyncio
async def test_guc_does_not_leak_across_pooled_connections(engine):
    """A transaction that errors must not leak its tenant GUC to the next checkout."""
    _eng, sm = engine

    tok = tenancy.set_current_tenant(TENANT_A)
    try:
        with pytest.raises(Exception):
            async with sm() as s:
                await s.execute(text("SELECT 1"))  # begins txn → GUC=A via listener
                await s.execute(text("SELECT 1/0"))  # force an error mid-transaction
    finally:
        tenancy.reset_current_tenant(tok)

    # Next request is tenant B — must see ONLY B, never A's leaked GUC.
    tok = tenancy.set_current_tenant(TENANT_B)
    try:
        assert await _titles_visible(sm) == ["casa B"]
    finally:
        tenancy.reset_current_tenant(tok)


@pytest.mark.asyncio
async def test_default_fallback_when_context_unset(engine):
    """Unset context resolves to the default tenant (V2 safety) — sees neither A nor B."""
    _eng, sm = engine
    tenancy.set_current_tenant(None)
    # Default tenant has no rows in this fixture → empty, and crucially not A/B's rows.
    assert await _titles_visible(sm) == []
