"""Phase 7 — Concurrency isolation hardening (two tenants in parallel).

The build plan (Phase 7) requires: *load test with two tenants in parallel; re-run
cross-tenant leakage tests under the connection pooler; verify transaction-scoped
GUC holds.*

Phase 1's ``tests/test_tenant_isolation.py`` proves isolation **sequentially** (one
``asyncio.run`` per tenant). This module proves it **concurrently**: many tasks
hitting a single shared pool at once, each task setting its own tenant ContextVar,
each seeing ONLY its own row. A leak (GUC bleeding across pooled checkouts, or a
ContextVar shared between tasks) would surface as a task seeing the other tenant's
row — the test fails if that ever happens.

Requires a real Postgres (RLS + set_config are Postgres-only) — skipped unless
``TEST_DATABASE_URL`` is set. Reuses the seeded standalone tables + non-superuser
app role from ``tests.test_tenant_isolation``. NEVER point at prod.

    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/inmueblebot_test \
        pytest tests/v3/test_concurrency_isolation.py
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import tenancy

# Reuse the Phase 1 fixtures/helpers verbatim so both suites exercise the same
# RLS policy, app role, and seeded data.
from tests.test_tenant_isolation import (  # noqa: E402
    TENANT_A,
    TENANT_B,
    _app_engine,
    _setup,
    _teardown,
)

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="TEST_DATABASE_URL not set (Postgres required for RLS tests)"
)

# Interleaved A/B tasks — enough to surface a ContextVar/GUC race if one exists.
_PARALLEL_TASKS = 40


@pytest.fixture()
def seeded():
    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


async def _one_tenant_read(engine, sm, tenant_id, expected_title: str) -> tuple[str, list[str]]:
    """One concurrent unit of work: set THIS task's tenant, read, assert isolation.

    Returns (expected, actually_seen) so the caller can assert across all tasks.
    The ContextVar is set inside the coroutine → it lives in this task's context
    copy only; sibling tasks must not observe it.
    """
    tok = tenancy.set_current_tenant(tenant_id)
    try:
        # Small yield so the scheduler interleaves A and B tasks (maximise contention).
        await asyncio.sleep(0)
        async with sm() as s:
            rows = await s.execute(text("SELECT title FROM t_props ORDER BY title"))
            seen = [r[0] for r in rows]
        return expected_title, seen
    finally:
        tenancy.reset_current_tenant(tok)


def test_parallel_two_tenants_no_leak(seeded):
    """40 interleaved A/B reads on one shared pool — each sees only its own row."""
    async def body():
        engine = _app_engine()
        sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            tasks = []
            for i in range(_PARALLEL_TASKS):
                if i % 2 == 0:
                    tasks.append(_one_tenant_read(engine, sm, TENANT_A, "casa A"))
                else:
                    tasks.append(_one_tenant_read(engine, sm, TENANT_B, "casa B"))
            return await asyncio.gather(*tasks)
        finally:
            await engine.dispose()

    results = asyncio.run(body())

    assert len(results) == _PARALLEL_TASKS
    for expected, seen in results:
        # Each task must see EXACTLY its own tenant's single row — no leakage.
        assert seen == [expected], f"isolation breach: expected {[expected]}, saw {seen}"


def test_repeated_pool_churn_holds_guc(seeded):
    """Re-run the parallel read several times to stress pooled-connection reuse.

    A transaction-scoped GUC (``set_config(..., true)``) must be re-applied on every
    checkout. If it were session-scoped (or leaked), a later round would see stale
    tenant state — this loop would catch it.
    """
    async def body():
        engine = _app_engine()
        sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            all_ok = True
            for _round in range(5):
                tasks = [
                    _one_tenant_read(engine, sm, TENANT_A, "casa A"),
                    _one_tenant_read(engine, sm, TENANT_B, "casa B"),
                    _one_tenant_read(engine, sm, TENANT_A, "casa A"),
                    _one_tenant_read(engine, sm, TENANT_B, "casa B"),
                ]
                for expected, seen in await asyncio.gather(*tasks):
                    if seen != [expected]:
                        all_ok = False
            return all_ok
        finally:
            await engine.dispose()

    assert asyncio.run(body()) is True


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
