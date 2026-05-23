"""
Seed script: 50 Oberá properties with images, categories, real street names.
Run: python3 seed_obera.py
"""
import asyncio, asyncpg, io, base64, random
from PIL import Image

DB = "postgresql://inmueblebot_user:XSqFG4FiC0q5OXXn1CiND25aHX076isu@dpg-d7vet8tckfvc73ehnjk0-a.oregon-postgres.render.com/inmueblebot_rfv1"

# ── 1. Generate placeholder JPEG images (tiny, ~2KB each) ──
def make_jpeg_b64(r, g, b, w=120, h=90):
    img = Image.new('RGB', (w, h), (r, g, b))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=60)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()

TYPE_IMAGES = {
    'departamento': [make_jpeg_b64(70, 130, 180), make_jpeg_b64(100, 149, 200), make_jpeg_b64(130, 160, 220)],
    'casa':         [make_jpeg_b64(180, 130, 70), make_jpeg_b64(200, 150, 100), make_jpeg_b64(220, 170, 130)],
    'terreno':      [make_jpeg_b64(80, 160, 80),  make_jpeg_b64(100, 180, 100), make_jpeg_b64(130, 200, 130)],
}
print(f"Generated {sum(len(v) for v in TYPE_IMAGES.values())} placeholder images")

# ── 2. Property data ──
random.seed(42)

STREETS = [
    "Av. San Martín", "Av. Sarmiento", "Av. Libertad", "Av. Italia", "Av. Andresito",
    "Av. de las Américas", "Calle Buenos Aires", "Calle Córdoba", "Calle Corrientes",
    "Calle Jujuy", "Calle Chaco", "Calle Santa Fe", "Calle 9 de Julio",
    "Calle Santiago del Estero", "Calle Brasil", "Calle Paraguay", "Calle Uruguay",
    "Calle Larrea", "Calle Gobernador Barreyro", "Calle Carhué", "Calle Finlandia",
    "Calle Suecia", "Calle Noruega", "Calle Dinamarca", "Calle España",
]

ZONES = [
    "Centro", "Barrio Norte", "Barrio Villa Svea", "UNAM", "Ruta 14",
    "Hospital Samic", "Barrio Schuster", "Barrio Docente", "Barrio 100 Viviendas",
    "Villa Stemberg", "Barrio Las Palmas", "Barrio Krause", "Barrio San Miguel",
    "Barrio Copisa", "Terminal",
]

def make_street():
    n = random.randint(100, 3500)
    street = random.choice(STREETS)
    return f"{street} {n}"

def make_desc(prop_type, beds, baths, area, zone, price, is_rent):
    if prop_type == 'departamento':
        templates = [
            f"Departamento luminoso de {beds} ambiente{'s' if beds > 1 else ''} en {zone}. {baths} baño{'s' if baths > 1 else ''}, {area}m². Ideal para {'familia pequeña' if beds >= 2 else 'una persona'}. Cerca de comercios y transporte público.",
            f"Moderno departamento en {zone} con {beds} dormitorio{'s' if beds > 1 else ''}. Cocina equipada, living amplio, {baths} baño{'s' if baths > 1 else ''}. Excelente ubicación.",
            f"Departamento en {zone}, {beds} ambientes, {area}m². {'Con balcón y' if beds >= 2 else ''} excelente iluminación natural. A pocas cuadras del centro.",
        ]
    elif prop_type == 'casa':
        templates = [
            f"Casa {'amplia ' if beds >= 4 else ''}en {zone} con {beds} dormitorio{'s' if beds > 1 else ''}, {baths} baño{'s' if baths > 1 else ''}, {area}m². {'Patio amplio con parrilla y garage.' if beds >= 3 else 'Patio y garage.'}",
            f"Hermosa casa en {zone}. {beds} ambientes, cocina-comedor integrado, {baths} baño{'s' if baths > 1 else ''}. {'Jardín y pileta.' if beds >= 3 else 'Jardín.'}",
            f"Propiedad en {zone}: casa de {beds} dormitorio{'s' if beds > 1 else ''} con {area}m² cubiertos. {'Quincho, lavadero y cochera doble.' if beds >= 3 else 'Cochera y lavadero.'}",
        ]
    else:
        templates = [
            f"Terreno en {zone}, {area}m². Ideal para construcción. Zona {'residencial' if area > 300 else 'tranquila'}. Todos los servicios disponibles.",
            f"Lote en {zone} de {area}m². Excelente ubicación, apto para {'casa familiar o duplex' if area > 250 else 'vivienda'}. Servicios al pie.",
            f"Terreno plano en {zone}, {area}m². {'Frente sobre avenida principal.' if random.random() > 0.5 else 'Sobre calle asfaltada.'}",
        ]
    return random.choice(templates)

properties = []

# ── 30 ALQUILER: 12 deptos, 12 casas, 6 terrenos ──
for i in range(12):
    beds = random.choice([1, 1, 2, 2, 2, 3, 3, 4])
    baths = max(1, beds - random.choice([0, 0, 1]))
    area = beds * random.randint(30, 55)
    zone = random.choice(ZONES)
    price = beds * random.randint(35000, 55000)
    properties.append({
        'id': i + 1,
        'title': f"Departamento {'en ' + zone + ' ' if random.random() > 0.3 else ''}{beds} amb",
        'type': 'alquiler', 'category': 'departamento',
        'location': f"{make_street()}, {zone}, Oberá, Misiones",
        'price': price, 'currency': 'ARS',
        'bedrooms': beds, 'bathrooms': baths, 'area_m2': area,
        'description': make_desc('departamento', beds, baths, area, zone, price, True),
        'status': 'available',
    })

for i in range(12):
    beds = random.choice([2, 2, 3, 3, 3, 4, 4, 5])
    baths = max(1, beds - random.choice([0, 0, 1, 1]))
    area = beds * random.randint(40, 70)
    zone = random.choice(ZONES)
    price = beds * random.randint(45000, 70000)
    properties.append({
        'id': 12 + i + 1,
        'title': f"Casa {beds} dormitorios {zone}",
        'type': 'alquiler', 'category': 'casa',
        'location': f"{make_street()}, {zone}, Oberá, Misiones",
        'price': price, 'currency': 'ARS',
        'bedrooms': beds, 'bathrooms': baths, 'area_m2': area,
        'description': make_desc('casa', beds, baths, area, zone, price, True),
        'status': 'available',
    })

for i in range(6):
    area = random.choice([200, 250, 300, 360, 400, 500, 600])
    zone = random.choice(ZONES)
    price = random.randint(40000, 90000)
    properties.append({
        'id': 24 + i + 1,
        'title': f"Terreno en {zone} {area}m²",
        'type': 'alquiler', 'category': 'terreno',
        'location': f"{make_street()}, {zone}, Oberá, Misiones",
        'price': price, 'currency': 'ARS',
        'bedrooms': None, 'bathrooms': None, 'area_m2': area,
        'description': make_desc('terreno', 0, 0, area, zone, price, True),
        'status': 'available',
    })

# ── 20 VENTA: 8 deptos, 8 casas, 4 terrenos ──
for i in range(8):
    beds = random.choice([1, 2, 2, 3, 3, 4])
    baths = max(1, beds - random.choice([0, 0, 1]))
    area = beds * random.randint(30, 55)
    zone = random.choice(ZONES)
    price = beds * random.randint(15000, 28000)
    properties.append({
        'id': 30 + i + 1,
        'title': f"Departamento {'en ' + zone if random.random() > 0.3 else ''}{beds} amb",
        'type': 'venta', 'category': 'departamento',
        'location': f"{make_street()}, {zone}, Oberá, Misiones",
        'price': price, 'currency': 'USD',
        'bedrooms': beds, 'bathrooms': baths, 'area_m2': area,
        'description': make_desc('departamento', beds, baths, area, zone, price, False),
        'status': 'available',
    })

for i in range(8):
    beds = random.choice([2, 3, 3, 4, 4, 5])
    baths = max(1, beds - random.choice([0, 0, 1]))
    area = beds * random.randint(45, 75)
    zone = random.choice(ZONES)
    price = beds * random.randint(20000, 40000)
    properties.append({
        'id': 38 + i + 1,
        'title': f"Casa {beds} dormitorios {zone}",
        'type': 'venta', 'category': 'casa',
        'location': f"{make_street()}, {zone}, Oberá, Misiones",
        'price': price, 'currency': 'USD',
        'bedrooms': beds, 'bathrooms': baths, 'area_m2': area,
        'description': make_desc('casa', beds, baths, area, zone, price, False),
        'status': 'available',
    })

for i in range(4):
    area = random.choice([300, 400, 500, 600, 800, 1000])
    zone = random.choice(ZONES)
    price = random.randint(15000, 60000)
    properties.append({
        'id': 46 + i + 1,
        'title': f"Terreno en {zone} {area}m²",
        'type': 'venta', 'category': 'terreno',
        'location': f"{make_street()}, {zone}, Oberá, Misiones",
        'price': price, 'currency': 'USD',
        'bedrooms': None, 'bathrooms': None, 'area_m2': area,
        'description': make_desc('terreno', 0, 0, area, zone, price, False),
        'status': 'available',
    })

print(f"Generated {len(properties)} property records")
print(f"  Alquiler: {sum(1 for p in properties if p['type']=='alquiler')}")
print(f"  Venta:    {sum(1 for p in properties if p['type']=='venta')}")
print(f"  Deptos:   {sum(1 for p in properties if p['category']=='departamento')}")
print(f"  Casas:    {sum(1 for p in properties if p['category']=='casa')}")
print(f"  Terrenos: {sum(1 for p in properties if p['category']=='terreno')}")

# ── 3. Seed DB ──
async def seed():
    conn = await asyncpg.connect(DB)
    await conn.execute("DELETE FROM properties")
    print("\nDeleted all existing properties")

    for p in properties:
        images = TYPE_IMAGES[p['category']]
        await conn.execute("""
            INSERT INTO properties (id, title, description, price, currency, type, location,
                                    bedrooms, bathrooms, area_m2, images, status, category, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
        """, p['id'], p['title'], p['description'], p['price'], p['currency'],
           p['type'], p['location'], p['bedrooms'], p['bathrooms'], p['area_m2'],
           images, p['status'], p['category'])

    count = await conn.fetchval("SELECT count(*) FROM properties")
    print(f"Inserted {count} properties")

    cats = await conn.fetch("SELECT category, count(*) as c FROM properties GROUP BY category ORDER BY category")
    print("Categories:", [(r['category'], r['c']) for r in cats])
    types = await conn.fetch("SELECT type, count(*) as c FROM properties GROUP BY type ORDER BY type")
    print("Types:", [(r['type'], r['c']) for r in types])

    # Test the exact search that was failing
    test = await conn.fetch("""
        SELECT id, title, category, bedrooms
        FROM properties
        WHERE type = 'alquiler' AND status = 'available' AND bedrooms >= 2
          AND (category = 'departamento'
               OR (category IS NULL AND (title ILIKE '%departamento%' OR title ILIKE '%depto%')))
        ORDER BY id
    """)
    print(f"\nSearch 'alquiler depto >=2 beds': {len(test)} results")
    for r in test:
        print(f"  ID={r['id']} | cat={r['category']} | beds={r['bedrooms']} | {r['title'][:50]}")

    await conn.close()

asyncio.run(seed())
print("\nDONE - 50 properties seeded successfully")
