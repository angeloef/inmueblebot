"""One-off seed: test data for city-variant resolution + reference_points search.

Inserts a handful of clearly-marked test properties so the two search features
shipped in commit 0ef0cf4 can be verified end-to-end against a real database:

  1. City spelling variants — the same town ("Leandro N. Alem") stored three ways
     ("Alem", "Leandro N. Alem", "LN Alem") so a query for one spelling should
     surface all three via resolve_city_variants().
  2. reference_points — properties whose JSONB reference_points array names a nearby
     landmark ("Hospital SAMIC", "Terminal de ómnibus") so a "cerca del hospital"
     query matches via _ref_points_like().

All rows are tagged extra_data['seed'] = SEED_TAG for trivial cleanup (see the
DELETE in docs/test-data-city-variants.md). The rows are attached to the SAME
tenant that owns the existing visible properties, so the bot reads them.

Run (PowerShell):
    $env:SEED_DATABASE_URL = "postgresql://USER:PASS@dpg-XXXX-a.oregon-postgres.render.com/DB"
    python scripts/seed_test_city_variants.py

The DSN must use the EXTERNAL Render host (…-a.<region>-postgres.render.com) when
run from outside Render's network. The password is read from the env var only —
never hardcode it here.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import sys

import asyncpg

SEED_TAG = "claude-city-variants-test"

# Default tenant (settings.DEFAULT_TENANT_ID) — the existing inmobiliaria the bot
# serves when no tenant context is set, which is exactly the path /simulate uses.
# RLS is FORCED on `properties`, so the GUC must be set to this BEFORE any read or
# write is visible. Override with env TENANT_ID if the deployment customized it.
_DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# (street/location-tail, city, zone, price, bedrooms, reference_points)
# location is built as "<street>, <zone>, <city>" to mirror admin.create_property.
_ROWS: list[dict] = [
    # ── City-variant family: all "Leandro N. Alem", spelled three ways ──
    {"street": "San Martín 100", "city": "Alem", "zone": "Centro",
     "price": 150000, "beds": 2, "baths": 1, "area": 60, "refs": []},
    {"street": "Belgrano 250", "city": "Leandro N. Alem", "zone": "Centro",
     "price": 185000, "beds": 3, "baths": 2, "area": 85, "refs": []},
    {"street": "Rivadavia 50", "city": "LN Alem", "zone": "Centro",
     "price": 165000, "beds": 2, "baths": 1, "area": 70, "refs": []},
    # ── reference_points family (Oberá, the default-tenant city) ──
    {"street": "Sarmiento 480", "city": "Oberá", "zone": "Centro",
     "price": 205000, "beds": 2, "baths": 2, "area": 78,
     "refs": ["Hospital SAMIC", "Plaza San Martín"]},
    {"street": "Av. Libertad 1200", "city": "Oberá", "zone": "Villa Bonita",
     "price": 178000, "beds": 3, "baths": 1, "area": 90,
     "refs": ["Terminal de ómnibus"]},
]


async def main() -> int:
    raw = os.environ.get("SEED_DATABASE_URL", "").strip()
    if not raw:
        print("ERROR: set SEED_DATABASE_URL (external Render host).", file=sys.stderr)
        return 2
    # asyncpg wants a clean libpq DSN — strip SQLAlchemy's +asyncpg and any sslmode.
    dsn = raw.replace("postgresql+asyncpg://", "postgresql://").split("?", 1)[0]

    sslctx = ssl.create_default_context()
    sslctx.check_hostname = False
    sslctx.verify_mode = ssl.CERT_NONE

    tenant_id = os.environ.get("TENANT_ID", _DEFAULT_TENANT_ID).strip()

    conn = await asyncpg.connect(dsn, ssl=sslctx, timeout=30)
    try:
        # RLS is FORCED on `properties`: announce the tenant FIRST, else every read
        # and the INSERT WITH CHECK see/allow nothing.
        await conn.execute(
            "SELECT set_config('app.current_tenant_id', $1, false)", tenant_id
        )
        existing = await conn.fetchval("SELECT count(*) FROM properties")
        print(f"Using tenant_id = {tenant_id}  (visible existing properties: {existing})")
        if existing == 0:
            print(
                "WARNING: 0 properties visible for this tenant. Either the tenant id "
                "is wrong (set TENANT_ID) or this is the wrong database.",
                file=sys.stderr,
            )

        # Idempotent: drop any previous rows from this seed before re-inserting.
        deleted = await conn.execute(
            "DELETE FROM properties WHERE extra_data->>'seed' = $1", SEED_TAG
        )
        print(f"Cleaned previous seed rows: {deleted}")

        next_id = (await conn.fetchval("SELECT COALESCE(MAX(id), 0) FROM properties")) + 1

        inserted = []
        for i, r in enumerate(_ROWS):
            pid = next_id + i
            location = f"{r['street']}, {r['zone']}, {r['city']}"
            title = f"Departamento {r['beds']} dormitorios {r['zone']}"
            extra = {
                "building_type": "apartment",
                "city": r["city"],
                "zone": r["zone"],
                "seed": SEED_TAG,
            }
            await conn.execute(
                """
                INSERT INTO properties
                  (id, tenant_id, title, description, price, currency, type,
                   location, bedrooms, bathrooms, area_m2, status, category,
                   extra_data, reference_points)
                VALUES
                  ($1, $2, $3, $4, $5, 'ARS', 'alquiler',
                   $6, $7, $8, $9, 'available', 'departamento',
                   $10::jsonb, $11::jsonb)
                """,
                pid, tenant_id, title,
                f"Propiedad de prueba ({SEED_TAG}).",
                r["price"], location, r["beds"], r["baths"], r["area"],
                json.dumps(extra), json.dumps(r["refs"]),
            )
            inserted.append((pid, r["city"], location, r["refs"]))
            print(f"  + ID:{pid}  city={r['city']!r}  refs={r['refs']}")

        print(f"\nInserted {len(inserted)} test properties under tenant {tenant_id}.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
