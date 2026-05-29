"""One-shot: delete all client data. Run on Render via:
   python3 scripts/cleanup_clients.py
"""
import asyncio
import sys
from sqlalchemy import text
from app.db.session import async_session_factory

TABLES = [
    "appointments",
    "conversations",
    "messages",
    "user_episodes",
    "users",
]


async def check_counts(session):
    """Show current row counts."""
    print("\n=== Current data ===")
    for table in TABLES:
        r = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
        count = r.scalar()
        print(f"  {table}: {count} rows")


async def delete_all(session):
    """Delete all rows from client tables."""
    print("\n=== Deleting ===")
    for table in TABLES:
        r = await session.execute(text(f"DELETE FROM {table}"))
        print(f"  {table}: {r.rowcount} rows deleted")
    await session.commit()
    print("\n=== Done. All client data deleted. ===")


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        async with async_session_factory() as session:
            await check_counts(session)
            await delete_all(session)
            await check_counts(session)
    else:
        async with async_session_factory() as session:
            await check_counts(session)
        print("\nRun with --confirm to actually delete.")
        print("  python3 scripts/cleanup_clients.py --confirm")


if __name__ == "__main__":
    asyncio.run(main())
