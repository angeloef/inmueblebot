"""
Download real property images and update DB with base64 data URIs.
Uses Unsplash free images - consistent, high-quality, real photos.
"""
import asyncio, asyncpg, base64, urllib.request, ssl

DB = "postgresql://inmueblebot_user:XSqFG4FiC0q5OXXn1CiND25aHX076isu@dpg-d7vet8tckfvc73ehnjk0-a.oregon-postgres.render.com/inmueblebot_rfv1"

# Unsplash free stock photo URLs (w=800 for reasonable size)
PHOTOS = {
    'departamento': [
        "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&q=80",  # modern living room
        "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800&q=80",      # apartment interior
        "https://images.unsplash.com/photo-1585412727339-54e4bae3bbf9?w=800&q=80",    # bright apartment
    ],
    'casa': [
        "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=800&q=80",    # modern house
        "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=800&q=80",    # house exterior
        "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=80",    # luxury house
    ],
    'terreno': [
        "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=800&q=80",    # green field
        "https://images.unsplash.com/photo-1500076656116-558758c991c1?w=800&q=80",    # land plot
        "https://images.unsplash.com/photo-1449844908441-8829872d2607?w=800&q=80",    # grassy lot
    ],
}

def download_image(url):
    """Download image and return as base64 data URI."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        data = resp.read()
    # Convert to JPEG data URI
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode()

async def update_db():
    print("Downloading images...")
    images = {}
    for category, urls in PHOTOS.items():
        imgs = []
        for i, url in enumerate(urls):
            try:
                b64 = download_image(url)
                imgs.append(b64)
                print(f"  {category} {i+1}/3: {len(b64)//1024}KB")
            except Exception as e:
                print(f"  {category} {i+1}/3: FAILED ({e}) — retrying with fallback")
                # Fallback: try with different params
                try:
                    b64 = download_image(url.replace('q=80', 'q=60'))
                    imgs.append(b64)
                    print(f"  {category} {i+1}/3: OK (fallback) {len(b64)//1024}KB")
                except Exception as e2:
                    print(f"  {category} {i+1}/3: FAILED again ({e2})")
        images[category] = imgs
        print(f"  {category}: {len(imgs)}/3 downloaded")
    
    # Update DB
    conn = await asyncpg.connect(DB)
    for category, imgs in images.items():
        if len(imgs) == 3:
            updated = await conn.execute(
                "UPDATE properties SET images = $1 WHERE category = $2",
                imgs, category
            )
            count = await conn.fetchval(
                "SELECT count(*) FROM properties WHERE category = $1", category
            )
            print(f"Updated {count} {category} properties with 3 images each")
    
    # Verify
    verify = await conn.fetch("""
        SELECT category, count(*), 
               bool_and(array_length(images,1)=3) as all_have_3,
               avg(length(images[1]))/1024 as avg_kb
        FROM properties GROUP BY category ORDER BY category
    """)
    print("\nVerification:")
    for r in verify:
        print(f"  {r['category']:15s} count={r['count']} all_3={r['all_have_3']} avg_size={r['avg_kb']:.0f}KB")
    
    await conn.close()

asyncio.run(update_db())
print("\nDone — images updated")
