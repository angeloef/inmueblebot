"""backfill_subscription_tiers.py — Migra suscripciones existentes al nuevo campo tier.

Las filas con plan=NULL o plan no reconocido reciben 'profesional' por defecto
(las inmobiliarias que ya pagaban/están en trial merecen el plan más completo).
Idempotente: no toca filas que ya tienen un plan válido.

Uso:
    python scripts/backfill_subscription_tiers.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.db.session import async_session_factory
from app.services.plans import CATALOG


async def backfill(dry_run: bool = False) -> int:
    valid_tiers = set(CATALOG)
    changed = 0
    async with async_session_factory() as session:
        from app.db.models import Subscription

        rows = list(await session.scalars(select(Subscription)))
        for sub in rows:
            if sub.plan not in valid_tiers:
                old = sub.plan
                if not dry_run:
                    sub.plan = "profesional"
                print(
                    f"[{'DRY' if dry_run else 'OK'}] "
                    f"tenant={sub.tenant_id} plan={old!r} → 'profesional'"
                )
                changed += 1
        if not dry_run and changed:
            await session.commit()
    print(f"\n{'Would update' if dry_run else 'Updated'} {changed} row(s).")
    return changed


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(backfill(dry_run=dry))
