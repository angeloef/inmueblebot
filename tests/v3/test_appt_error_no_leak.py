"""Plan #17: cancel/reschedule never leak the raw exception to the user.

Previously a failure returned "No pude cancelar la visita: {e}" with {e} being the
raw asyncpg/SQL error. Now the user gets a generic Spanish retry message; the detail
is logged server-side via logger.error.

Offline — the DB session factory is patched to raise a sentinel.
"""

import asyncio
import unittest
from unittest.mock import patch

from app.tools.v2 import cancel_appointment as cancel_mod
from app.tools.v2 import reschedule_appointment as resched_mod

_SENTINEL = "asyncpg.ForeignKeyViolationError: secret table detail"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _raising_factory(*a, **k):
    raise RuntimeError(_SENTINEL)


class TestApptErrorNoLeak(unittest.TestCase):

    def test_cancel_hides_raw_exception(self):
        with patch.object(cancel_mod, "async_session_factory", _raising_factory):
            out = _run(cancel_mod.cancel_appointment(cual="jueves"))
        self.assertNotIn(_SENTINEL, out)
        self.assertNotIn("asyncpg", out)
        self.assertIn("cancelar", out.lower())
        self.assertTrue(out.endswith("?"))  # offers a retry, not a stack trace

    def test_reschedule_hides_raw_exception(self):
        with patch.object(resched_mod, "async_session_factory", _raising_factory):
            out = _run(resched_mod.reschedule_appointment(dia="jueves", horario="15:00"))
        self.assertNotIn(_SENTINEL, out)
        self.assertNotIn("asyncpg", out)
        self.assertIn("reprogramar", out.lower())


if __name__ == "__main__":
    unittest.main()
