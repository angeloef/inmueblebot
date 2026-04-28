import asyncio
from sqlalchemy import text
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
from app.db.session import async_session_factory

async def check():
    try:
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT id, title, images FROM properties WHERE images IS NOT NULL LIMIT 1"))
            row = result.fetchone()
            if row:
                print(f"[OK] DB SUCCESS: Property '{row[1]}' has images: {row[2]}")
            else:
                print("[FAIL] DB FAILURE: No properties have images. Run scripts/populate_test_images.py again.")
    except Exception as e:
        print(f"[ERROR] ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(check())
