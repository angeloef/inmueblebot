#!/usr/bin/env python3
"""
Seed Script: Recover 9 properties lost during Frankfurt→Oregon DB migration.

This script inserts 9 properties into the Oregon PostgreSQL database using
asyncpg, with the correct column mapping from the old Frankfurt schema to
the new Oregon schema. It is fully idempotent — it checks for existing
properties by original_id before inserting.

Old Frankfurt Schema → New Oregon Schema Mapping:
  old: property_type (Enum)     →  new: extra_data['building_type']
  old: address + city           →  new: location
  old: price (Float)            →  new: price (Integer)
  old: area (Float)             →  new: area_m2 (Integer)
  old: images (Text/JSON str)   →  new: images[] (ARRAY[Text])
  old: featured (Boolean)       →  new: extra_data['featured']
  old: active (Boolean)         →  new: status ('available' | 'sold')

Usage:
  python scripts/seed_oregon_properties.py

Environment:
  DATABASE_URL — PostgreSQL connection URL (supports postgresql:// or
                 postgresql+asyncpg:// formats; +asyncpg is auto-stripped).
  If not set, defaults to the local Docker URL.
"""

import asyncio
import json
import os
import re
import sys
from typing import Optional

import asyncpg


# ──────────────────────────────────────────────────────────────────────────────
# 1. DATABASE URL RESOLUTION
# ──────────────────────────────────────────────────────────────────────────────

def resolve_db_url() -> str:
    """
    Resolve the DATABASE_URL for raw asyncpg usage.
    Strips the '+asyncpg' driver suffix if present, and normalises ssl params.
    """
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raw = "postgresql://postgres:postgres@db:5432/inmueblebot"
        print(f"[seed] ⚠  No DATABASE_URL set; using default: {raw}")

    # Strip +asyncpg suffix — raw asyncpg expects postgresql:// or postgres://
    url = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    url = url.replace("?sslmode=require", "?ssl=require")
    url = url.replace("&sslmode=require", "&ssl=require")
    return url


# ──────────────────────────────────────────────────────────────────────────────
# 2. THE 9 LOST PROPERTIES — Realistic Argentina real estate data
#    Each dict uses the *old* Frankfurt schema field names so the mapping
#    logic is explicit and reusable if a real dump is ever found.
# ──────────────────────────────────────────────────────────────────────────────

LOST_PROPERTIES = [
    {
        "id": 1,
        "title": "Departamento 2 ambientes en Palermo Soho",
        "description": (
            "Excelente departamento en el corazón de Palermo Soho. "
            "Cocina integrada, balcón parisino con vista a la calle, "
            "living comedor amplio, y baño completo. A pasos del "
            "subte D y de los mejores bares y restaurantes de la ciudad."
        ),
        "property_type": "apartment",
        "address": "Av. Scalabrini Ortiz 1520",
        "city": "CABA",
        "price": 85000.0,
        "bedrooms": 2,
        "bathrooms": 1,
        "area": 55.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2",
            "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267",
        ]),
        "featured": True,
        "active": True,
    },
    {
        "id": 2,
        "title": "Casa con jardín en Nordelta",
        "description": (
            "Hermosa casa de 3 dormitorios en el barrio cerrado Los Sauces, "
            "Nordelta. Amplio jardín con parrilla, cocina comedor diario, "
            "living con chimenea, garaje para 2 autos. Cuota de "
            "mantención incluida. A 15 min del centro de Tigre."
        ),
        "property_type": "house",
        "address": "Calle Los Talas 342",
        "city": "Nordelta, Tigre",
        "price": 325000.0,
        "bedrooms": 3,
        "bathrooms": 2,
        "area": 180.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1564013799919-ab600027ffc6",
            "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83",
        ]),
        "featured": False,
        "active": True,
    },
    {
        "id": 3,
        "title": "Local comercial en Microcentro porteño",
        "description": (
            "Local a la calle en pleno Microcentro, a metros de la "
            "peatonal Florida y la galería Pacífico. Cortina metálica "
            "eléctrica, depósito posterior, baño privado. Ideal para "
            "indumentaria o gastronomía. Alto tránsito peatonal."
        ),
        "property_type": "commercial",
        "address": "Florida 740, Local 3",
        "city": "CABA",
        "price": 210000.0,
        "bedrooms": 0,
        "bathrooms": 1,
        "area": 42.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1441986300917-64674bd600d8",
        ]),
        "featured": False,
        "active": True,
    },
    {
        "id": 4,
        "title": "PH en Nueva Córdoba con terraza",
        "description": (
            "Hermoso PH en el barrio más trendy de Córdoba capital. "
            "Terraza propia de 30 m² con vista a la ciudad, piso de "
            "porcellanato, cocina con isla, placares amurados. "
            "A 3 cuadras del Buen Pastor y la Cañada."
        ),
        "property_type": "apartment",
        "address": "Av. Hipólito Yrigoyen 560",
        "city": "Córdoba",
        "price": 118000.0,
        "bedrooms": 2,
        "bathrooms": 2,
        "area": 75.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1560185007-cde436f6a4d0",
            "https://images.unsplash.com/photo-1560185127-6ed189bf02f4",
        ]),
        "featured": True,
        "active": True,
    },
    {
        "id": 5,
        "title": "Casa quinta en zona de Carlos Paz",
        "description": (
            "Casa quinta con pileta en las sierras de Carlos Paz. "
            "Parque de 800 m² con árboles frutales, quincho con horno, "
            "y galería vidriada. 3 dormitorios, 2 baños, cocina "
            "amplia. Ideal para fin de semana o renta vacacional."
        ),
        "property_type": "house",
        "address": "Ruta Provincial 28, Km 6",
        "city": "Villa Carlos Paz, Córdoba",
        "price": 195000.0,
        "bedrooms": 3,
        "bathrooms": 2,
        "area": 140.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1564013799919-ab600027ffc6",
            "https://images.unsplash.com/photo-1580587771525-78b9dba3b914",
        ]),
        "featured": False,
        "active": True,
    },
    {
        "id": 6,
        "title": "Departamento céntrico en Rosario",
        "description": (
            "Amplio departamento en Rosario centro, a media cuadra del "
            "Parque Independencia. Living comedor con ventanales, "
            "cocina separada con lavadero, 2 dormitorios con placares, "
            "baño completo más toilette. Edificio con pileta y SUM."
        ),
        "property_type": "apartment",
        "address": "Cochabamba 830, Piso 6",
        "city": "Rosario, Santa Fe",
        "price": 95000.0,
        "bedrooms": 2,
        "bathrooms": 2,
        "area": 68.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2",
            "https://images.unsplash.com/photo-1493809842364-78817add7ffb",
        ]),
        "featured": False,
        "active": True,
    },
    {
        "id": 7,
        "title": "Terreno en loteo privado de Mendoza",
        "description": (
            "Terreno de 450 m² en loteo privado de Chacras de Coria. "
            "Con vista a la Cordillera de los Andes, servicios de "
            "luz, gas, agua y cloaca ya instalados. Escritura en mano. "
            "Ideal para construcción de casa de fin de semana."
        ),
        "property_type": "land",
        "address": "Calle Los Olivos s/n, Lote 14",
        "city": "Chacras de Coria, Mendoza",
        "price": 62000.0,
        "bedrooms": None,
        "bathrooms": None,
        "area": 450.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1500382017468-9049fed747ef",
        ]),
        "featured": False,
        "active": True,
    },
    {
        "id": 8,
        "title": "Oficina ejecutiva en Puerto Madero",
        "description": (
            "Oficina premium en torre corporativa de Puerto Madero. "
            "Vidriado al piso con vista al río, piso técnico, "
            "instalación de aire central, baño privado, cocina. "
            "4 estacionamientos incluidos. Acceso 24/7 con seguridad."
        ),
        "property_type": "office",
        "address": "Macacha Güemes 250, Piso 12",
        "city": "CABA",
        "price": 420000.0,
        "bedrooms": 0,
        "bathrooms": 1,
        "area": 95.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1497366216548-37526070297c",
            "https://images.unsplash.com/photo-1497366811353-6870744d04b2",
        ]),
        "featured": True,
        "active": True,
    },
    {
        "id": 9,
        "title": "Cabaña de montaña en Bariloche",
        "description": (
            "Acogedora cabaña de estilo alpino en el km 18 de Av. "
            "Exequiel Bustillo, camino a Llao Llao. Vista al lago "
            "Nahuel Huapi, hogar a leña, cocina completa, 2 dormitorios, "
            "1 baño con hidromasaje. Terraza con parrilla. "
            "A 200 m de la playa."
        ),
        "property_type": "house",
        "address": "Av. Exequiel Bustillo Km 18, Casa 7",
        "city": "San Carlos de Bariloche, Río Negro",
        "price": 275000.0,
        "bedrooms": 2,
        "bathrooms": 1,
        "area": 85.0,
        "images": json.dumps([
            "https://images.unsplash.com/photo-1518780664697-55e3ad937233",
        ]),
        "featured": False,
        "active": True,
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# 3. COLUMN MAPPING — Old Frankfurt → New Oregon
# ──────────────────────────────────────────────────────────────────────────────

# Map old PropertyType enum values → extra_data building_type strings
BUILDING_TYPE_MAP = {
    "apartment": "apartment",
    "house": "house",
    "land": "land",
    "commercial": "commercial",
    "office": "office",
}


def _parse_images(old_images: Optional[str]) -> Optional[list]:
    """Parse a JSON string of image URLs into a list."""
    if not old_images:
        return None
    try:
        parsed = json.loads(old_images)
        if isinstance(parsed, list):
            return parsed
        return [str(parsed)]
    except (json.JSONDecodeError, TypeError):
        return None


def map_old_to_new(old: dict) -> dict:
    """Map a dict with old Frankfurt schema fields to new Oregon schema fields."""

    # location = address + city
    address = old.get("address", "")
    city = old.get("city", "")
    location = f"{address}, {city}" if address and city else (address or city)

    # price — convert float to int
    price_raw = old.get("price", 0)
    price = int(round(price_raw)) if isinstance(price_raw, (int, float)) else 0

    # area → area_m2
    area_raw = old.get("area")
    area_m2 = int(round(area_raw)) if isinstance(area_raw, (int, float)) else None

    # images — JSON string → array
    images = _parse_images(old.get("images"))

    # property_type → extra_data.building_type
    ptype = old.get("property_type", "apartment")
    building_type = BUILDING_TYPE_MAP.get(ptype, ptype)

    # featured → extra_data.featured
    featured = bool(old.get("featured", False))

    # active → status
    active = bool(old.get("active", True))
    status = "available" if active else "sold"

    # Build extra_data
    extra_data = {
        "building_type": building_type,
        "featured": featured,
    }

    return {
        "id": old["id"],
        "original_id": old["id"],
        "title": old.get("title", "Sin título"),
        "description": old.get("description"),
        "price": price,
        "currency": "USD",
        "type": "venta",  # most properties are for sale
        "location": location,
        "lat": None,
        "lng": None,
        "bedrooms": old.get("bedrooms"),
        "bathrooms": old.get("bathrooms"),
        "area_m2": area_m2,
        "images": images,
        "status": status,
        "extra_data": extra_data,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. IDEMPOTENCY CHECK & INSERT
# ──────────────────────────────────────────────────────────────────────────────


async def get_existing_original_ids(conn) -> set:
    """Return the set of original_id values already present in the DB."""
    rows = await conn.fetch("SELECT original_id FROM properties WHERE original_id IS NOT NULL")
    return {row["original_id"] for row in rows}


async def insert_property(conn, data: dict) -> bool:
    """
    Insert a single property record. Returns True if inserted, False if skipped.
    Uses a parameterised query with the correct Oregon schema columns.
    """
    # Check if this original_id already exists
    existing = await conn.fetchrow(
        "SELECT id FROM properties WHERE CAST(original_id AS text) = CAST($1 AS text)",
        str(data["original_id"])
    )
    if existing:
        print(f"  ⏭  Property #{data['id']} ({data['title']}) — already exists, skipping.")
        return False

    # Serialise extra_data and images to JSON for asyncpg
    extra_data_json = json.dumps(data["extra_data"]) if data["extra_data"] else None
    images_list = data["images"]  # asyncpg handles Python lists → ARRAY

    await conn.execute(
        """
        INSERT INTO properties (
            id, original_id, title, description, price, currency,
            type, location, lat, lng, bedrooms, bathrooms,
            area_m2, images, status, extra_data
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11, $12,
            $13, $14, $15, $16::jsonb
        )
        """,
        data["id"],
        data["original_id"],
        data["title"],
        data["description"],
        data["price"],
        data["currency"],
        data["type"],
        data["location"],
        data["lat"],
        data["lng"],
        data["bedrooms"],
        data["bathrooms"],
        data["area_m2"],
        images_list,
        data["status"],
        extra_data_json,
    )
    print(f"  ✅ Property #{data['id']} ({data['title']}) — INSERTED.")
    return True


async def seed() -> int:
    """
    Main seeding logic.
    Returns the number of properties inserted (0 if all already exist).
    """
    db_url = resolve_db_url()
    print(f"[seed] 🔗 Connecting to: {re.sub(r'://[^@]+@', '://***@', db_url)}")
    print(f"[seed] 📦 Target: {len(LOST_PROPERTIES)} lost properties to recover")
    print()

    conn = await asyncpg.connect(db_url)

    try:
        # Idempotency check — see what's already there
        existing_ids = await get_existing_original_ids(conn)
        print(f"[seed] 🔍 Found {len(existing_ids)} existing properties in DB (by original_id).")
        print()

        inserted = 0
        skipped = 0
        for old_prop in LOST_PROPERTIES:
            new_data = map_old_to_new(old_prop)
            if new_data["original_id"] in existing_ids:
                print(f"  ⏭  Property #{new_data['id']} (original_id={new_data['original_id']}) — already exists, skipping.")
                skipped += 1
                continue
            ok = await insert_property(conn, new_data)
            if ok:
                inserted += 1
            else:
                skipped += 1

        print()
        print(f"[seed] ─────────────────────────────────────")
        print(f"[seed] ✅ Done — {inserted} inserted, {skipped} skipped.")
        print(f"[seed] ─────────────────────────────────────")
        return inserted

    finally:
        await conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# 5. CLI ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """Run the seed script."""
    inserted = asyncio.run(seed())
    sys.exit(0 if inserted >= 0 else 1)


if __name__ == "__main__":
    main()
