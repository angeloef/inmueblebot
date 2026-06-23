"""Seed script for local eval env (knowledge agent v4 testing).

Creates a test tenant, loads properties from tests/obera_properties.json,
and inserts FAQ entries so the knowledge grounding eval has real data.

Usage:
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/inmueblebot \
    REDIS_URL=redis://localhost:6379/0 \
    python -m tests.eval.seed_local

Guards against running on prod: aborts if DATABASE_URL contains render.com/supabase.
"""
from __future__ import annotations

import asyncio
import os
import sys
from uuid import UUID, uuid4

_DB_URL = os.environ.get("DATABASE_URL", "")

_PROD_HINTS = ("render.com", "supabase", ".internal")
if any(h in _DB_URL for h in _PROD_HINTS):
    sys.exit(
        f"[seed_local] Aborting — DATABASE_URL looks like prod: {_DB_URL[:60]}...\n"
        "Set DATABASE_URL to your local docker DB before running this script."
    )

# ── constants ────────────────────────────────────────────────────────────────

TEST_TENANT_SLUG = "test-local"
TEST_TENANT_NAME = "Inmobiliaria Test Local"

FAQ_ENTRIES = [
    {
        "question": "¿Qué requisitos necesito para alquilar?",
        "answer": "Para alquilar necesitás: DNI vigente, garantía propietaria (título de propiedad de la persona garante), recibo de sueldo de los últimos 3 meses y referencia laboral. Para extranjeros se aceptan avales bancarios.",
        "category": "requisitos",
        "tags": ["alquiler", "garantía", "requisitos", "documentos"],
    },
    {
        "question": "¿Qué tipo de garantías aceptan?",
        "answer": "Aceptamos garantía propietaria (inmueble en Misiones o provincia limítrofe), recibo de sueldo con antigüedad mínima de 6 meses, o seguro de caución. No aceptamos fiadores personales sin propiedades.",
        "category": "requisitos",
        "tags": ["garantía", "fiador", "seguro caución"],
    },
    {
        "question": "¿Cuáles son los horarios de atención?",
        "answer": "Atendemos de lunes a viernes de 8:30 a 12:30 y de 16:00 a 20:00. Los sábados de 9:00 a 12:00. Domingos y feriados cerramos.",
        "category": "horarios",
        "tags": ["horarios", "atención", "oficina"],
    },
    {
        "question": "¿Cuánto dura el contrato de alquiler?",
        "answer": "Los contratos de alquiler residencial tienen una duración mínima de 2 años (24 meses), según la ley de alquileres vigente. El precio se ajusta según el índice ICL (Índice para Contratos de Locación) cada 6 meses.",
        "category": "contratos",
        "tags": ["contrato", "duración", "ajuste", "ICL"],
    },
    {
        "question": "¿Se pueden tener mascotas en las propiedades en alquiler?",
        "answer": "Depende de cada propietario. En general aceptamos mascotas pequeñas (hasta 10 kg) con depósito adicional. Consultá por la propiedad específica ya que cada caso se evalúa individualmente.",
        "category": "condiciones",
        "tags": ["mascotas", "animales", "depósito"],
    },
]


async def _ensure_tenant(session) -> UUID:
    """Get or create the test tenant, returns its UUID."""
    from sqlalchemy import select
    from app.db.models.tenant import Tenant

    result = await session.execute(
        select(Tenant).where(Tenant.slug == TEST_TENANT_SLUG)
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        print(f"[OK] Tenant already exists: {tenant.slug} ({tenant.id})")
        return tenant.id

    tenant = Tenant(
        id=uuid4(),
        slug=TEST_TENANT_SLUG,
        display_name=TEST_TENANT_NAME,
        business_hours="Lunes a viernes 8:30-12:30 y 16:00-20:00. Sábados 9:00-12:00.",
        timezone="America/Argentina/Cordoba",
        status="active",
    )
    session.add(tenant)
    await session.flush()
    print(f"[OK] Created test tenant: {tenant.slug} ({tenant.id})")
    return tenant.id


async def _seed_faqs(session, tenant_id: UUID) -> None:
    """Insert FAQ entries for the test tenant (skips if already present)."""
    from sqlalchemy import select, func
    from app.db.models.faq import FAQ

    count_result = await session.execute(
        select(func.count()).select_from(FAQ).where(FAQ.tenant_id == tenant_id)
    )
    existing = count_result.scalar_one()
    if existing >= len(FAQ_ENTRIES):
        print(f"[OK] FAQs already seeded ({existing} entries).")
        return

    for i, entry in enumerate(FAQ_ENTRIES):
        faq = FAQ(
            tenant_id=tenant_id,
            question=entry["question"],
            answer=entry["answer"],
            category=entry.get("category"),
            tags=entry.get("tags"),
            order=i,
            active=True,
        )
        session.add(faq)

    print(f"[OK] Inserted {len(FAQ_ENTRIES)} FAQ entries.")


async def _seed_properties(tenant_id: UUID) -> None:
    """Reuse app/db/seed.py logic but pinned to the test tenant."""
    import json
    from pathlib import Path
    from sqlalchemy import select, func
    from app.db.models import Property
    from app.db.session import async_session_factory

    json_path = Path(__file__).parent.parent / "obera_properties.json"
    if not json_path.exists():
        print(f"[SKIP] {json_path} not found — run `python tests/seed_properties.py` first.")
        return

    with open(json_path, encoding="utf-8") as f:
        raw = json.load(f)

    async with async_session_factory() as db:
        count_result = await db.execute(
            select(func.count()).select_from(Property).where(Property.tenant_id == tenant_id)
        )
        if count_result.scalar_one() > 0:
            print("[OK] Properties already seeded for test tenant.")
            return

        import re
        for item in raw:
            pid = item.get("id")
            price_raw = item.get("price", "0")
            currency = "ARS"
            price_val = 0
            if isinstance(price_raw, str):
                currency = "USD" if "USD" in price_raw else "ARS"
                m = re.search(r"[\d,]+", price_raw.replace("$", ""))
                if m:
                    price_val = int(m.group().replace(",", ""))
            elif isinstance(price_raw, (int, float)):
                price_val = int(price_raw)

            location = ""
            if item.get("address") and item.get("city"):
                location = f"{item['address']}, {item['city']}"
            elif item.get("city"):
                location = item["city"]

            prop = Property(
                id=pid,
                tenant_id=tenant_id,
                original_id=pid,
                title=item.get("title"),
                description=item.get("description"),
                price=price_val,
                currency=currency,
                type=item.get("operation", "alquiler"),
                category=item.get("type"),
                location=location,
                bedrooms=item.get("bedrooms"),
                bathrooms=item.get("bathrooms"),
                area_m2=item.get("area"),
                status="available",
                extra_data={"kind": item.get("type")},
            )
            db.add(prop)

        await db.commit()
        print(f"[OK] Inserted {len(raw)} properties for test tenant.")


async def main() -> None:
    from app.db.session import async_session_factory

    print(f"[seed_local] DB: {_DB_URL[:60]}...")

    async with async_session_factory() as db:
        tenant_id = await _ensure_tenant(db)
        await _seed_faqs(db, tenant_id)
        await db.commit()

    await _seed_properties(tenant_id)
    print("[seed_local] Done. Test tenant ready for local eval.")
    print(f"[seed_local] TENANT_ID={tenant_id}")


if __name__ == "__main__":
    asyncio.run(main())
