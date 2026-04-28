#!/usr/bin/env python
import asyncio
import sys

async def main():
    print("Seeding database...")
    
    from app.db.seed import seed_properties
    await seed_properties()
    print("Properties seeded")
    
    sys.path.insert(0, '.')
    exec(open('populate_test_images.py').read())
    print("Images populated")
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())