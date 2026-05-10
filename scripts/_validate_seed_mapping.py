#!/usr/bin/env python3
"""
Quick dry-run validator for the seed script's column mapping logic.
Does NOT require asyncpg or any project dependencies.
"""
import json
from typing import Optional

# ── inline the mapping logic from seed_oregon_properties.py ──

BUILDING_TYPE_MAP = {
    "apartment": "apartment",
    "house": "house",
    "land": "land",
    "commercial": "commercial",
    "office": "office",
}

def _parse_images(old_images: Optional[str]) -> Optional[list]:
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
    address = old.get("address", "")
    city = old.get("city", "")
    location = f"{address}, {city}" if address and city else (address or city)

    price_raw = old.get("price", 0)
    price = int(round(price_raw)) if isinstance(price_raw, (int, float)) else 0

    area_raw = old.get("area")
    area_m2 = int(round(area_raw)) if isinstance(area_raw, (int, float)) else None

    images = _parse_images(old.get("images"))

    ptype = old.get("property_type", "apartment")
    building_type = BUILDING_TYPE_MAP.get(ptype, ptype)

    featured = bool(old.get("featured", False))
    active = bool(old.get("active", True))
    status = "available" if active else "sold"

    extra_data = {"building_type": building_type, "featured": featured}

    return {
        "id": old["id"],
        "original_id": old["id"],
        "title": old.get("title", "Sin título"),
        "description": old.get("description"),
        "price": price,
        "currency": "USD",
        "type": "venta",
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

# ── Data ──

LOST_PROPERTIES = [
    {
        "id": 1,
        "title": "Departamento 2 ambientes en Palermo Soho",
        "description": "Excelente departamento en el corazón de Palermo Soho. Cocina integrada, balcón parisino.",
        "property_type": "apartment",
        "address": "Av. Scalabrini Ortiz 1520",
        "city": "CABA",
        "price": 85000.0,
        "bedrooms": 2,
        "bathrooms": 1,
        "area": 55.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1560448204-e02f11c3d0e2"]),
        "featured": True,
        "active": True,
    },
    {
        "id": 2,
        "title": "Casa con jardín en Nordelta",
        "description": "Hermosa casa de 3 dormitorios en barrio cerrado Los Sauces, Nordelta.",
        "property_type": "house",
        "address": "Calle Los Talas 342",
        "city": "Nordelta, Tigre",
        "price": 325000.0,
        "bedrooms": 3,
        "bathrooms": 2,
        "area": 180.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1564013799919-ab600027ffc6"]),
        "featured": False,
        "active": True,
    },
    {
        "id": 3,
        "title": "Local comercial en Microcentro porteño",
        "description": "Local a la calle en pleno Microcentro.",
        "property_type": "commercial",
        "address": "Florida 740, Local 3",
        "city": "CABA",
        "price": 210000.0,
        "bedrooms": 0,
        "bathrooms": 1,
        "area": 42.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1441986300917-64674bd600d8"]),
        "featured": False,
        "active": True,
    },
    {
        "id": 4,
        "title": "PH en Nueva Córdoba con terraza",
        "description": "Hermoso PH en Nueva Córdoba capital. Terraza propia de 30 m².",
        "property_type": "apartment",
        "address": "Av. Hipólito Yrigoyen 560",
        "city": "Córdoba",
        "price": 118000.0,
        "bedrooms": 2,
        "bathrooms": 2,
        "area": 75.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1560185007-cde436f6a4d0"]),
        "featured": True,
        "active": True,
    },
    {
        "id": 5,
        "title": "Casa quinta en zona de Carlos Paz",
        "description": "Casa quinta con pileta en las sierras de Carlos Paz.",
        "property_type": "house",
        "address": "Ruta Provincial 28, Km 6",
        "city": "Villa Carlos Paz, Córdoba",
        "price": 195000.0,
        "bedrooms": 3,
        "bathrooms": 2,
        "area": 140.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1564013799919-ab600027ffc6"]),
        "featured": False,
        "active": True,
    },
    {
        "id": 6,
        "title": "Departamento céntrico en Rosario",
        "description": "Amplio departamento en Rosario centro.",
        "property_type": "apartment",
        "address": "Cochabamba 830, Piso 6",
        "city": "Rosario, Santa Fe",
        "price": 95000.0,
        "bedrooms": 2,
        "bathrooms": 2,
        "area": 68.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1560448204-e02f11c3d0e2"]),
        "featured": False,
        "active": True,
    },
    {
        "id": 7,
        "title": "Terreno en loteo privado de Mendoza",
        "description": "Terreno de 450 m² en loteo privado de Chacras de Coria.",
        "property_type": "land",
        "address": "Calle Los Olivos s/n, Lote 14",
        "city": "Chacras de Coria, Mendoza",
        "price": 62000.0,
        "bedrooms": None,
        "bathrooms": None,
        "area": 450.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1500382017468-9049fed747ef"]),
        "featured": False,
        "active": True,
    },
    {
        "id": 8,
        "title": "Oficina ejecutiva en Puerto Madero",
        "description": "Oficina premium en torre corporativa de Puerto Madero.",
        "property_type": "office",
        "address": "Macacha Güemes 250, Piso 12",
        "city": "CABA",
        "price": 420000.0,
        "bedrooms": 0,
        "bathrooms": 1,
        "area": 95.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1497366216548-37526070297c"]),
        "featured": True,
        "active": True,
    },
    {
        "id": 9,
        "title": "Cabaña de montaña en Bariloche",
        "description": "Acogedora cabaña de estilo alpino en el km 18 de Av. Exequiel Bustillo.",
        "property_type": "house",
        "address": "Av. Exequiel Bustillo Km 18, Casa 7",
        "city": "San Carlos de Bariloche, Río Negro",
        "price": 275000.0,
        "bedrooms": 2,
        "bathrooms": 1,
        "area": 85.0,
        "images": json.dumps(["https://images.unsplash.com/photo-1518780664697-55e3ad937233"]),
        "featured": False,
        "active": True,
    },
]

# ── Run validation ──

print("=" * 80)
print("DRY RUN — Column Mapping Validation (Frankfurt → Oregon)")
print("=" * 80)

errors = 0
for old in LOST_PROPERTIES:
    new = map_old_to_new(old)
    pid = new["id"]

    issues = []

    # Required non-null fields
    for field in ("id", "original_id", "title", "type", "status", "currency", "location"):
        val = new.get(field)
        if val is None or val == "":
            issues.append(f"{field} is empty/null")

    # Type constraints
    if new["type"] not in ("venta", "alquiler"):
        issues.append(f"type='{new['type']}' not in (venta, alquiler)")
    if new["status"] not in ("available", "reserved", "sold", "rented"):
        issues.append(f"status='{new['status']}' not valid")

    # Price must be int
    if not isinstance(new["price"], int):
        issues.append(f"price is {type(new['price']).__name__}, expected int")

    # area_m2 must be int or None
    area = new.get("area_m2")
    if area is not None and not isinstance(area, int):
        issues.append(f"area_m2 is {type(area).__name__}, expected int or None")

    # images must be list or None
    imgs = new.get("images")
    if imgs is not None and not isinstance(imgs, list):
        issues.append(f"images is {type(imgs).__name__}, expected list or None")

    # extra_data must have building_type and featured
    ed = new.get("extra_data", {})
    if not isinstance(ed, dict):
        issues.append(f"extra_data is {type(ed).__name__}, expected dict")
    else:
        if "building_type" not in ed:
            issues.append("extra_data missing building_type")
        if "featured" not in ed:
            issues.append("extra_data missing featured")

    # Nullable ints
    for field in ("bedrooms", "bathrooms"):
        val = new.get(field)
        if val is not None and not isinstance(val, int):
            issues.append(f"{field} is {type(val).__name__}, expected int or None")

    status_icon = "❌" if issues else "✅"
    print(f"  {status_icon} PROP #{pid}: {new['title'][:50]:50s}")
    print(f"     type={new['type']:8s} | status={new['status']:10s} | "
          f"price=${new['price']:<8,d} | curr={new['currency']}")
    print(f"     location={new['location'][:60]}")
    print(f"     extra_data={json.dumps(ed)}")
    if new["bedrooms"] is not None:
        print(f"     bedrooms={new['bedrooms']} | bathrooms={new['bathrooms']} | "
              f"area_m2={new['area_m2']} | images_count={len(imgs) if imgs else 0}")
    else:
        print(f"     bedrooms=None | bathrooms=None | "
              f"area_m2={new['area_m2']} | images_count={len(imgs) if imgs else 0}")

    if issues:
        for iss in issues:
            print(f"     ⚠  {iss}")
        errors += 1

print()
print("─" * 80)
if errors == 0:
    print(f"✅ ALL {len(LOST_PROPERTIES)} PROPERTIES VALIDATED — no issues found.")
else:
    print(f"❌ {errors} properties have issues.")
print("─" * 80)
