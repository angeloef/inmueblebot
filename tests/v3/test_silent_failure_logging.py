"""Plan #15: belief load/save failures are logged at WARNING, not swallowed.

A belief load failure used to silently start a fresh conversation (no log) and a
save failure was logged at DEBUG — both invisible in production. These tests patch
Redis to fail and assert a WARNING is emitted (the turn still degrades gracefully).

All offline — Redis is stubbed; no real I/O.
"""

import asyncio
import unittest
from unittest.mock import patch

from loguru import logger

from app.routers.v3 import belief as belief_mod


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _LogCapture:
    """Capture loguru WARNING+ messages into a list for assertions."""

    def __enter__(self):
        self.messages: list[str] = []
        self._sink_id = logger.add(lambda m: self.messages.append(str(m)), level="WARNING")
        return self

    def __exit__(self, *exc):
        logger.remove(self._sink_id)
        return False


async def _raise_redis():
    raise RuntimeError("redis down")


class TestSilentFailureLogging(unittest.TestCase):

    def test_load_failure_logs_warning_and_returns_fresh(self):
        with patch("app.core.tenancy.tenant_redis_key", return_value="k"), \
             patch.object(belief_mod, "_get_redis", _raise_redis), \
             _LogCapture() as cap:
            result = _run(belief_mod.load_belief_v5("sess-1"))
        self.assertEqual(result.session_id, "sess-1")  # graceful fresh belief
        self.assertTrue(any("load_belief_v5 failed" in m for m in cap.messages), cap.messages)

    def test_save_failure_logs_warning(self):
        b = belief_mod.BeliefStateV5(session_id="sess-2")
        with patch("app.core.tenancy.tenant_redis_key", return_value="k"), \
             patch.object(belief_mod, "_get_redis", _raise_redis), \
             _LogCapture() as cap:
            _run(belief_mod.save_belief_v5(b))  # must not raise
        self.assertTrue(any("save_belief_v5 failed" in m for m in cap.messages), cap.messages)


if __name__ == "__main__":
    unittest.main()
