"""Plan #4: per-user serialization via get_user_lock.

The webhook now wraps each turn's dispatch in ``async with get_user_lock(phone)``
so two rapid messages from the same phone can't run concurrent belief
read-modify-write turns (which raced and lost slots/history). These tests verify
the locking primitive the webhook depends on: same phone → mutual exclusion,
different phones → independent.

NOTE: the end-to-end "2 messages 1.2s apart → both in history" assertion needs
Redis + the LLM and is exercised in the live integration env, not here.

All offline.
"""

import asyncio
import unittest

from app.core.session import get_user_lock


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestUserLockSerialization(unittest.TestCase):

    def test_same_phone_returns_same_lock(self):
        a = get_user_lock("549111234")
        b = get_user_lock("549111234")
        self.assertIs(a, b)

    def test_mutual_exclusion_same_phone(self):
        """Two tasks on the same phone never execute the critical section at once."""
        phone = "549110000001"
        state = {"inside": 0, "max_overlap": 0}

        async def worker():
            async with get_user_lock(phone):
                state["inside"] += 1
                state["max_overlap"] = max(state["max_overlap"], state["inside"])
                await asyncio.sleep(0.02)  # hold long enough to overlap if unlocked
                state["inside"] -= 1

        async def main():
            await asyncio.gather(*(worker() for _ in range(5)))

        _run(main())
        self.assertEqual(state["max_overlap"], 1, "lock allowed concurrent entry")

    def test_different_phones_can_overlap(self):
        """Distinct phones use distinct locks and may run concurrently."""
        state = {"inside": 0, "max_overlap": 0}

        async def worker(phone):
            async with get_user_lock(phone):
                state["inside"] += 1
                state["max_overlap"] = max(state["max_overlap"], state["inside"])
                await asyncio.sleep(0.02)
                state["inside"] -= 1

        async def main():
            await asyncio.gather(*(worker(f"54911000{i}") for i in range(4)))

        _run(main())
        self.assertGreater(state["max_overlap"], 1, "distinct phones should overlap")


if __name__ == "__main__":
    unittest.main()
