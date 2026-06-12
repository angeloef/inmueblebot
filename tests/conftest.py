"""Shared pytest fixtures.

The app uses a single module-level async engine (``app.db.session.async_engine``) whose
asyncpg connections are bound to the event loop that created them. With pytest-asyncio in
``auto`` mode each test runs on its own function-scoped loop, so a connection pooled during
test A is invalid in test B ("Event loop is closed"). Disposing the pool after every test
forces each test to open fresh connections on its own loop.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
async def _dispose_async_engine_between_tests():
    """Dispose the async engine's connection pool after each test (cross-loop safety)."""
    yield
    try:
        from app.db import session as _session

        engine = getattr(_session, "async_engine", None)
        if engine is not None:
            await engine.dispose()
    except Exception:
        # Never let teardown cleanup fail a test run.
        pass
