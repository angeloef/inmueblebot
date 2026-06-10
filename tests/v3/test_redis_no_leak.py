"""Plan #18: the Redis connection is always returned, even on get/set error.

aclose() previously ran only on the happy path, so any get()/set() exception
leaked a connection. The try/finally guarantees release. These fakes raise inside
get()/set() and assert aclose() was still awaited (and the turn degrades, not raises).

Offline — Redis is a fake; no real I/O.
"""

import asyncio
import unittest
from unittest.mock import patch

from app.routers.v3 import belief as belief_mod


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeRedis:
    def __init__(self, *, raise_on):
        self.raise_on = raise_on
        self.closed = False

    async def get(self, key):
        if self.raise_on == "get":
            raise RuntimeError("get boom")
        return None

    async def set(self, key, value, ex=None):
        if self.raise_on == "set":
            raise RuntimeError("set boom")

    async def aclose(self):
        self.closed = True


class TestRedisNoLeak(unittest.TestCase):

    def test_load_closes_connection_on_get_error(self):
        fake = _FakeRedis(raise_on="get")

        async def _get_redis():
            return fake

        with patch("app.core.tenancy.tenant_redis_key", return_value="k"), \
             patch.object(belief_mod, "_get_redis", _get_redis):
            result = _run(belief_mod.load_belief_v5("sess-1"))  # must not raise

        self.assertTrue(fake.closed, "connection must be closed after a get() error")
        self.assertEqual(result.session_id, "sess-1")

    def test_save_closes_connection_on_set_error(self):
        fake = _FakeRedis(raise_on="set")

        async def _get_redis():
            return fake

        b = belief_mod.BeliefStateV5(session_id="sess-2")
        with patch("app.core.tenancy.tenant_redis_key", return_value="k"), \
             patch.object(belief_mod, "_get_redis", _get_redis):
            _run(belief_mod.save_belief_v5(b))  # must not raise

        self.assertTrue(fake.closed, "connection must be closed after a set() error")

    def test_load_closes_connection_on_success(self):
        fake = _FakeRedis(raise_on=None)

        async def _get_redis():
            return fake

        with patch("app.core.tenancy.tenant_redis_key", return_value="k"), \
             patch.object(belief_mod, "_get_redis", _get_redis):
            _run(belief_mod.load_belief_v5("sess-3"))

        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
