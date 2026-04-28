"""
Generate 50 properties for Obera, Misiones - CONSOLE OUTPUT
Run: python tests/seed_properties.py
"""
import random

PROPERTY_TYPES = ["casa", "departamento", "duplex", "ph"]
ZONAS = [
    "Centro", "Belvedere", "Villa Quebracho", "San Miguel", "Barrio Industrial",
    "Santa Rosa", "Los Pioneros", "Puerto Oro", "Parque Nacional",
    "Barrio Norte", "Barrio Sur", "Villa Nueva", "Obera"
]

STREETS_CENTRO = [
    "Av. Sarmiento", "Av. San Martin", "Calle San Luis", "Calle Posadas",
    "Calle Cordoba", "Av. Roque Gonzalez", "Calle Missionera", "Calle Felix de Azara"
]

STREETS_BARRIOS = [
    "Calle Los Andes", "Calle Monteagudo", "Calle Uruguay", "Calle Brasil",
    "Av. Juan XXIII", "Calle Matera", "Calle Tuyuti", "Calle Yapeyu",
    "Pasaje Las Lilas", "Av. Marcelo"
]

DESCRIPTIONS = [
    "Excelente ubicacion, muy iluminado",
    "Cerca de escuelas y shops",
    "Patio con asador, ideal para familias",
    "Cochera cubierta, seguridad 24hs",
    "Kitchen integrada, moderno",
    "Vista al parque, entorno tranquilo",
    "Recien refaccionado, como nuevo",
    "Pileta, SUM propio",
    "Amplios ambientes",
    "Balcon con vista panoramica"
]

def generate_phone():
    return f"+54 9{random.randint(3755, 3799)}{random.randint(100, 999)}{random.randint(100, 999)}"

print("="*70)
print("PROPERTIES FOR OBERA, MISIONES - 50 LISTINGS")
print("="*70)
print()

properties = []

for i in range(1, 51):
    # Location
    if random.random() < 0.7:
        zona = "Centro"
        street = random.choice(STREETS_CENTRO)
        street_number = random.randint(100, 1500)
    else:
        zona = random.choice(ZONAS)
        street = random.choice(STREETS_BARRIOS)
        street_number = random.randint(1, 800)
    
    prop_type = random.choice(PROPERTY_TYPES)
    bedrooms = random.randint(1, 4)
    bathrooms = random.randint(1, 3)
    area_m2 = random.randint(35, 200)
    
    # Price
    if prop_type == "departamento":
        price = random.randint(80000, 250000)
        bedrooms = min(bedrooms, 2)
        area_m2 = random.randint(35, 80)
    elif prop_type == "casa":
        price = random.randint(150000, 500000)
        bedrooms = random.randint(2, 4)
        area_m2 = random.randint(80, 200)
    else:
        price = random.randint(100000, 350000)
    
    # 85% alquiler, 15% venta
    if random.random() < 0.15:
        operation = "venta"
        currency = "USD"
        price_usd = price // 900
        price_display = f"${price_usd:,} USD"
    else:
        operation = "alquiler"
        currency = "ARS"
        price_display = f"${price:,} ARS/mes"
    
    prop = {
        "id": i,
        "title": f"{prop_type.capitalize()} en {zona}, Oberá",
        "description": f"{random.choice(DESCRIPTIONS)}. {bedrooms} dormitorio(s), {bathrooms} baño(s), {area_m2}m².",
        "type": prop_type,
        "operation": operation,
        "address": f"{street} {street_number}",
        "city": "Oberá",
        "state": "Misiones",
        "price": price_display,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "area": area_m2,
        "owner_phone": generate_phone()
    }
    properties.append(prop)
    
    print(f"[{i:02d}] {prop['title']}")
    print(f"      {prop['type']} | {prop['operation']} | {prop['price']}")
    print(f"      {prop['address']}, {prop['city']}, {prop['state']}")
    print(f"      {prop['bedrooms']} dorms | {prop['bathrooms']} baths | {prop['area']}m²")
    print()

print("="*70)
print(f"TOTAL: {len(properties)} properties")
print("="*70)

# Summary
rentals = sum(1 for p in properties if p['operation'] == 'alquiler')
sales = sum(1 for p in properties if p['operation'] == 'venta')
print(f"Alquiler: {rentals}")
print(f"Venta: {sales}")
print()

# Save to JSON file
import json
with open("tests/obera_properties.json", "w", encoding="utf-8") as f:
    json.dump(properties, f, ensure_ascii=False, indent=2)
print("Saved to: tests/obera_properties.json")