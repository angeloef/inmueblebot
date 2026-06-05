"""
Script de seed para crear propiedades de ejemplo.
Ejecutar: python -m app.db.seed
"""
import asyncio
from datetime import datetime
import os
import json
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Property
from app.core.config import get_settings


# Propiedades de ejemplo (seed) - opcional: cargas desde tests/obera_properties.json cuando exista
SAMPLE_PROPERTIES = []

# Try to load seed data from tests/obera_properties.json to preserve original ids (1..N)
try:
    seed_json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'obera_properties.json'))
    if os.path.exists(seed_json_path):
        with open(seed_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list) and data:
                for item in data:
                    # Ensure id is int
                    pid = int(item.get('id', 0)) if isinstance(item.get('id', 0), int) else None
                    if pid is None:
                        continue
                    # Map to Property fields; be robust to missing keys
                    # Handle different JSON field names: address/city vs location
                    location = item.get('location') or item.get('address') or item.get('city', '')
                    if item.get('city') and item.get('address'):
                        location = f"{item.get('address')}, {item.get('city')}"
                    
                    # Parse price - handle "$XXX,XXX" format with currency
                    price = item.get('price', 0)
                    currency = "USD"  # default
                    if isinstance(price, str):
                        import re
                        # Detect currency: ARS, USD, etc.
                        currency_match = re.search(r'(ARS|USD|U\$S)', price, re.IGNORECASE)
                        if currency_match:
                            currency = currency_match.group(1).upper()
                            if currency == "U$S":
                                currency = "USD"
                        # Extract numeric value
                        price_match = re.search(r'[\d,]+', price.replace('$', '').replace('ARS', '').replace('USD', '').replace('U$S', ''))
                        if price_match:
                            price = int(price_match.group().replace(',', ''))
                    
                    SAMPLE_PROPERTIES.append({
                        'id': pid,
                        'title': item.get('title'),
                        'description': item.get('description'),
                        'type': item.get('operation') or 'alquiler',  # venta/alquiler mapped to Property.type
                        # Physical type (casa/departamento/ph/terreno) → Property.category,
                        # per the model's documented intent. search_properties filters on it.
                        'category': item.get('type'),
                        'currency': currency,
                        'location': location,
                        'lat': item.get('lat'),
                        'lng': item.get('lng'),
                        'bedrooms': item.get('bedrooms'),
                        'bathrooms': item.get('bathrooms'),
                        'area_m2': item.get('area_m2') or item.get('area', None),
                        'price': price,
                        'images': item.get('images'),
                        'extra_data': {
                            'kind': item.get('type'),  # property kind: casa, departamento, etc.
                            **item.get('extra_data', {})
                        }
                    })
except Exception as e:
    print(f"[seed] Could not load JSON seed: {e}")


async def seed_properties(force: bool = False):
    """Inserta propiedades de ejemplo en la base de datos.
    
    Args:
        force: If True, deletes existing properties before seeding
    """
    from app.db.session import async_session_factory
    from sqlalchemy import select, func, delete
    
    async with async_session_factory() as session:
        # Verificar si ya hay propiedades
        result = await session.execute(select(func.count()).select_from(Property))
        count = result.scalar_one()
        
        if count > 0:
            if force:
                print(f"[INFO] Deleting existing {count} properties...")
                await session.execute(delete(Property))
                await session.commit()
            else:
                print(f"[INFO] Already {count} properties exist. Skipping seed.")
                return
        
        # Tenant scoping: set tenant_id EXPLICITLY to the default tenant. The ORM
        # inserts tenant_id=NULL otherwise (the model has no server_default, so the
        # DB-level column DEFAULT added by migration 0002 is overridden), which makes
        # every tenant-scoped query (_scoped_select) skip these rows.
        from app.core.tenancy import default_tenant_id
        _tid = default_tenant_id()

        # Crear propiedades (seeded from JSON if loaded)
        for prop_data in SAMPLE_PROPERTIES:
            prop = Property(
                id=prop_data.get("id"),
                tenant_id=_tid,
                original_id=prop_data.get("id"),
                external_id=prop_data.get("external_id"),
                title=prop_data.get("title"),
                description=prop_data.get("description"),
                price=int(prop_data.get("price")) if isinstance(prop_data.get("price"), (int, float)) else 0,
                currency=prop_data.get("currency", "USD"),
                type=prop_data.get("type"),
                category=prop_data.get("category"),
                location=prop_data.get("location"),
                lat=prop_data.get("lat"),
                lng=prop_data.get("lng"),
                bedrooms=prop_data.get("bedrooms"),
                bathrooms=prop_data.get("bathrooms"),
                area_m2=prop_data.get("area_m2"),
                images=prop_data.get("images"),
                extra_data=prop_data.get("extra_data"),
                status=prop_data.get("status", "available"),
            )
            session.add(prop)
        await session.commit()
        if SAMPLE_PROPERTIES:
            print(f"[OK] {len(SAMPLE_PROPERTIES)} properties created from seed.json")


if __name__ == "__main__":
    print("Running seed...")
    asyncio.run(seed_properties())
