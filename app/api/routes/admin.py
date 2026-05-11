from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import get_settings
from app.core.memory import MemoryManager
import uuid as _uuid

# Admin API uses a global MemoryManager for operations like user context reset
memory_manager = MemoryManager()

router = APIRouter(prefix="/admin", tags=["admin"])

# ── Sync DB session (lazy init) ─────────────────────────────────────────────
# The admin endpoints use a sync SQLAlchemy session independent from the
# async session used by the bot.  psycopg2 is required; if missing at import
# time we fail gracefully when the endpoint is actually called.

_engine = None
_SessionLocal = None
_migration_done = False


def _run_startup_migration(engine):
    """One-time schema migrations so admin endpoints work correctly.

    Idempotent — uses IF NOT EXISTS / IF EXISTS / DO blocks throughout.
    Migrations:
      1. Add extra_data JSONB to users  (stores email / role / notes for admin-created leads)
      2. Make appointments.user_id nullable  (admin can create events without a linked contact)
      3. Drop ck_appointment_type constraint  (allow 'call' and custom types, not just visit/signing/meeting)
      4. Rename properties.operation_type → type  (Frankfurt→Oregon column rename fix)
      5. Migrate properties.property_type → extra_data['building_type']  (old Enum → JSONB)
      6. Change properties.images to TEXT[]  (VARCHAR(255)[] truncates base64 URIs)
      7. Rename properties.latitude → lat  (Frankfurt→Oregon column rename fix)
      8. Rename properties.longitude → lng  (Frankfurt→Oregon column rename fix)
      9. Rename properties.total_area → area_m2  (Frankfurt→Oregon column rename fix)
      10. Cast properties.extra_data from TEXT to JSONB  (MUST happen before Fix 11)
      11. Migrate properties.city → extra_data['city']  (old flat column → JSONB, needs JSONB extra_data)
      12. Rename appointments.appointment_type → type  (Frankfurt→Oregon column rename fix)
    """
    global _migration_done
    if _migration_done:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_data JSONB"
            ))
            conn.execute(text(
                "ALTER TABLE appointments ALTER COLUMN user_id DROP NOT NULL"
            ))
            conn.execute(text(
                "ALTER TABLE appointments ALTER COLUMN property_id DROP NOT NULL"
            ))
            conn.execute(text(
                "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ck_appointment_type"
            ))
            conn.execute(text(
                "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ck_appointment_status"
            ))
            # ── Fix 1: Rename operation_type → type ─────────────────────
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'operation_type'
                    ) THEN
                        ALTER TABLE properties RENAME COLUMN operation_type TO type;
                    END IF;
                END $$;
            """))
            # ── Fix 2: Migrate property_type (old Enum) → extra_data ────
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'property_type'
                    ) THEN
                        UPDATE properties
                        SET extra_data = COALESCE(extra_data, '{}'::jsonb) || jsonb_build_object('building_type', property_type::text)
                        WHERE property_type IS NOT NULL;
                        ALTER TABLE properties DROP COLUMN IF EXISTS property_type;
                    END IF;
                END $$;
            """))
            # ── Fix 3: Widen images column from VARCHAR(255)[] to TEXT[] ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'images'
                          AND udt_name = '_varchar'
                    ) THEN
                        ALTER TABLE properties ALTER COLUMN images TYPE TEXT[] USING images::text[];
                    END IF;
                END $$;
            """))
            # ── Fix 4: Rename latitude → lat (Frankfurt→Oregon column rename) ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'latitude'
                    ) THEN
                        ALTER TABLE properties RENAME COLUMN latitude TO lat;
                    END IF;
                END $$;
            """))
            # ── Fix 5: Rename longitude → lng (Frankfurt→Oregon column rename) ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'longitude'
                    ) THEN
                        ALTER TABLE properties RENAME COLUMN longitude TO lng;
                    END IF;
                END $$;
            """))
            # ── Fix 6: Rename total_area → area_m2 (Frankfurt→Oregon column rename) ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'total_area'
                    ) THEN
                        ALTER TABLE properties RENAME COLUMN total_area TO area_m2;
                    END IF;
                END $$;
            """))
            # ── Fix 7: Cast extra_data from TEXT to JSONB if needed (MUST run before city migration) ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'extra_data'
                          AND udt_name = 'text'
                    ) THEN
                        ALTER TABLE properties ALTER COLUMN extra_data TYPE JSONB USING extra_data::jsonb;
                    END IF;
                END $$;
            """))
            # ── Fix 8: Migrate city → extra_data['city'] + drop city column ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'extra_data'
                          AND udt_name = 'text'
                    ) THEN
                        ALTER TABLE properties ALTER COLUMN extra_data TYPE JSONB USING extra_data::jsonb;
                    END IF;
                END $$;
            """))
            # ── Fix 7: Migrate city → extra_data['city'] + drop city column ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'properties' AND column_name = 'city'
                    ) THEN
                        UPDATE properties
                        SET extra_data = COALESCE(extra_data, '{}'::jsonb) || jsonb_build_object('city', city)
                        WHERE city IS NOT NULL AND city != '';
                        ALTER TABLE properties DROP COLUMN IF EXISTS city;
                    END IF;
                END $$;
            """))
            # ── Fix 9: Rename appointments.appointment_type → type ─
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'appointments' AND column_name = 'appointment_type'
                    ) THEN
                        ALTER TABLE appointments RENAME COLUMN appointment_type TO type;
                    END IF;
                END $$;
            """))
            # ── Fix 13: Create faq_entries table if not exists ──────────
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS faq_entries (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    category VARCHAR(100),
                    tags TEXT[],
                    "order" INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                )
            """))
            conn.commit()
        _migration_done = True
    except Exception as exc:
        # Log but don't crash — already migrated or DB unavailable at startup
        import logging
        logging.getLogger(__name__).warning("Startup migration warning: %s", exc)
        _migration_done = True   # don't retry on every request


def _get_sync_session() -> Session:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        url = (get_settings().resolved_database_url
               .replace("+asyncpg", "")
               .replace("?ssl=require", "?sslmode=require")
               .replace("&ssl=require", "&sslmode=require"))
        _engine = create_engine(url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        _run_startup_migration(_engine)
    return _SessionLocal()


def get_db():
    db = _get_sync_session()
    try:
        yield db
    finally:
        db.close()


# ── Auth ───────────────────────────────────────────────────────────────────────

def verify_admin_api_key(x_api_key: str = Header(None), x_admin_api_key: str = Header(None)):
    api_key = x_api_key or x_admin_api_key
    if not api_key or api_key != get_settings().ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@router.get("/debug/users")
def debug_users():
    """Diagnóstico: ejecuta query de users y retorna el error completo."""
    import traceback
    try:
        db = _get_sync_session()
        from sqlalchemy import text as _text
        result = db.execute(_text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [r[0] for r in result.fetchall()]
        try:
            from app.db.models import User
            users = db.query(User).limit(1).all()
            user_count = db.query(User).count()
            first = _user_to_dict(users[0]) if users else None
            return {"tables": tables, "user_count": user_count, "first_user": first}
        except Exception as e2:
            return {"tables": tables, "user_error": traceback.format_exc()}
        finally:
            db.close()
    except Exception as e:
        return {"fatal_error": traceback.format_exc()}


# ── Schemas ────────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None       # → User.whatsapp_phone (generated if empty)
    email: Optional[str] = None       # → stored in User.extra_data
    role: Optional[str] = "prospect"  # → stored in User.extra_data
    notes: Optional[str] = None       # → stored in User.extra_data


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None


class PropertyCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    building_type: Optional[str] = None   # 'apartment','house',… → Property.extra_data
    operation: Optional[str] = "venta"    # 'venta' or 'alquiler' → Property.type
    location: Optional[str] = None        # Property.location
    city: Optional[str] = None            # City name → Property.extra_data['city']
    price: Optional[int] = 0              # Property.price (integer cents/USD)
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_m2: Optional[int] = None
    currency: str = "USD"
    status: str = "available"             # 'available','reserved','sold','rented'
    images: Optional[List[str]] = None    # List of image URLs


class AppointmentCreate(BaseModel):
    start_time: Optional[str] = None   # ISO datetime, e.g. "2026-05-12T10:30:00"
    end_time: Optional[str] = None     # ISO datetime (default: start + 1 h)
    type: Optional[str] = "visit"      # 'visit', 'call', or any string
    user_id: Optional[str] = None      # UUID string → Appointment.user_id (nullable after migration)
    property_id: Optional[int] = None
    status: Optional[str] = "confirmed"
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    type: Optional[str] = None
    user_id: Optional[str] = None
    property_id: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class HandoffRequest(BaseModel):
    reason: Optional[str] = "user_requested"


# ── Serialization helpers ──────────────────────────────────────────────────────

_ROLE_TO_STATUS = {"prospect": "new", "tenant": "converted", "owner": "new", "lost": "lost"}


def _user_to_dict(u):
    """Serializa User al shape que espera el dashboard (compatible con toClient())."""
    extra = (getattr(u, 'extra_data', None) or {})
    role = extra.get("role", "prospect")
    return {
        "id": str(u.id),
        "phone": u.whatsapp_phone,
        "name": u.name,
        "email": extra.get("email"),
        "status": _ROLE_TO_STATUS.get(role, "new"),   # toClient() maps status → role
        "notes": extra.get("notes"),
        "tags": [],
        "lead_score": getattr(u, 'lead_score', 0) or 0,
        "last_interaction": u.last_interaction.isoformat() if u.last_interaction else None,
        "updated_at": u.last_interaction.isoformat() if u.last_interaction else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _prop_to_dict(p):
    """Serializa Property al shape que espera el dashboard (compatible con toProperty())."""
    extra = p.extra_data or {}
    city = extra.get("city", "")
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "property_type": extra.get("building_type", ""),   # toProperty() reads property_type
        "address": p.location,                             # toProperty() reads address/location
        "city": city,                                      # toProperty() reads city → neigh
        "neigh": city,                                     # Extra alias so the dashboard Neighborhood field is populated
        "price": p.price,
        "bedrooms": p.bedrooms,
        "bathrooms": p.bathrooms,
        "area": p.area_m2,                                 # toProperty() reads area/area_m2
        "images": p.images or [],
        "featured": False,
        "active": p.status in ("available", "reserved"),
        "status": p.status,
        "type": p.type,                                    # 'venta' or 'alquiler'
        "currency": getattr(p, "currency", "USD"),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _apt_to_dict(a):
    """Serializa Appointment al shape que espera el dashboard (compatible con toEvent())."""
    return {
        "id": str(a.id),
        "lead_id": str(a.user_id) if a.user_id else None,   # toEvent() reads lead_id
        "user_id": str(a.user_id) if a.user_id else None,
        "property_id": a.property_id,
        "scheduled_at": a.start_time.isoformat() if a.start_time else None,  # alias
        "start_time": a.start_time.isoformat() if a.start_time else None,
        "end_time": a.end_time.isoformat() if a.end_time else None,
        "type": a.type,
        "status": a.status,
        "notes": a.notes,
        "calendar_event_id": a.calendar_event_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ── Leads (→ users table) ──────────────────────────────────────────────────────

@router.get("/leads")
def list_leads(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import User
    try:
        users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
        return {"leads": [_user_to_dict(u) for u in users], "total": len(users)}
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=traceback.format_exc())


@router.get("/leads/{lead_id}")
def get_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import User
    try:
        uid = _uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format (expected UUID)")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _user_to_dict(user)


@router.post("/leads")
def create_lead(
    data: LeadCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import User
    # whatsapp_phone is NOT NULL unique — generate a placeholder for admin-created leads
    phone = data.phone or f"admin_{_uuid.uuid4().hex[:10]}"
    extra = {
        "email": data.email,
        "role": data.role or "prospect",
        "notes": data.notes,
    }
    user = User(whatsapp_phone=phone, name=data.name)
    # extra_data column is added by startup migration; set it after object creation
    try:
        user.extra_data = extra
    except AttributeError:
        pass   # column not yet migrated — data stored on next request
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_dict(user)


@router.patch("/leads/{lead_id}")
def update_lead(
    lead_id: str,
    data: LeadUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import User
    try:
        uid = _uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format (expected UUID)")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Lead not found")

    if data.name is not None:
        user.name = data.name

    updates = data.model_dump(exclude_unset=True)
    extra = dict(getattr(user, 'extra_data', None) or {})
    for key in ("email", "role", "notes"):
        if key in updates:
            extra[key] = updates[key]
    try:
        user.extra_data = extra
    except AttributeError:
        pass

    db.commit()
    return {"status": "updated", "lead_id": lead_id}


@router.delete("/leads/{lead_id}")
def delete_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import User
    try:
        uid = _uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format (expected UUID)")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(user)
    db.commit()
    return {"status": "deleted", "lead_id": lead_id}


@router.post("/users/{phone}/reset")
def reset_user_context(
    phone: str,
    _: bool = Depends(verify_admin_api_key),
):
    """Reset conversation context for a user by phone number.
    Clears Redis keys, in-memory fallback, and PostgreSQL preferences.
    Useful for testing — ensures the bot starts fresh on next message."""
    import asyncio
    try:
        asyncio.run(memory_manager.reset_user_context(phone))
        return {"status": "reset", "phone": phone}
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=traceback.format_exc())



# ── Properties ─────────────────────────────────────────────────────────────────

@router.get("/properties")
def list_properties(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Property
    props = db.query(Property).filter(Property.status != "sold").all()
    return {"properties": [_prop_to_dict(p) for p in props], "total": len(props)}


@router.post("/properties")
def create_property(
    data: PropertyCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Property
    op = data.operation if data.operation in ("venta", "alquiler") else "venta"

    # Build location string — include city suffix if city was provided
    # but not already embedded in the location
    location = data.location or ""
    if data.city and data.city.strip():
        city_str = data.city.strip()
        if city_str.lower() not in location.lower():
            # Append city to location, e.g. "calle eight 222, centro → "calle eight 222, centro, Oberá"
            separator = ", " if location else ""
            location = f"{location}{separator}{city_str}"

    prop = Property(
        id=_next_property_id(db),
        title=data.title or data.location or "Sin título",
        description=data.description,
        type=op,
        location=location,
        price=data.price or 0,
        currency=data.currency,
        bedrooms=data.bedrooms,
        bathrooms=data.bathrooms,
        area_m2=data.area_m2,
        status=data.status if data.status in ("available", "reserved", "sold", "rented") else "available",
        extra_data={"building_type": data.building_type, "city": data.city or ""},
        images=data.images,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return _prop_to_dict(prop)


def _next_property_id(db: Session) -> int:
    """Property uses manual integer PK (autoincrement=False). Find the next free ID."""
    from app.db.models import Property
    from sqlalchemy import func
    max_id = db.query(func.max(Property.id)).scalar() or 0
    return max_id + 1


@router.patch("/properties/{prop_id}")
def update_property(
    prop_id: int,
    data: PropertyCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Property
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    updates = data.model_dump(exclude_unset=True)
    if "operation" in updates:
        op = updates.pop("operation")
        prop.type = op if op in ("venta", "alquiler") else "venta"
    if "location" in updates:
        prop.location = updates.pop("location")
    if "area_m2" in updates:
        prop.area_m2 = updates.pop("area_m2")
    if "status" in updates:
        s = updates.pop("status")
        prop.status = s if s in ("available", "reserved", "sold", "rented") else "available"
    if "building_type" in updates:
        extra = dict(prop.extra_data or {})
        extra["building_type"] = updates.pop("building_type")
        prop.extra_data = extra
    if "city" in updates:
        extra = dict(prop.extra_data or {})
        extra["city"] = updates.pop("city")
        prop.extra_data = extra
    if "currency" in updates:
        prop.currency = updates.pop("currency")
    if "images" in updates and updates["images"] is not None:
        prop.images = updates.pop("images")

    for k, v in updates.items():
        if hasattr(prop, k):
            setattr(prop, k, v)

    db.commit()
    return _prop_to_dict(prop)


@router.delete("/properties/{prop_id}")
def delete_property(
    prop_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Property
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    prop.status = "sold"   # soft delete
    db.commit()
    return {"status": "deleted", "property_id": prop_id}


# ── Appointments ───────────────────────────────────────────────────────────────

@router.get("/appointments")
def list_appointments(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Appointment
    query = db.query(Appointment)
    if status:
        query = query.filter(Appointment.status == status)
    apts = query.order_by(Appointment.start_time.desc()).limit(limit).all()
    return {"appointments": [_apt_to_dict(a) for a in apts], "total": len(apts)}


@router.post("/appointments")
def create_appointment(
    data: AppointmentCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Appointment
    from datetime import datetime, timezone, timedelta

    start = None
    if data.start_time:
        try:
            start = datetime.fromisoformat(data.start_time)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid start_time: {data.start_time!r}")

    end = None
    if data.end_time:
        try:
            end = datetime.fromisoformat(data.end_time)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid end_time: {data.end_time!r}")
    elif start:
        end = start + timedelta(hours=1)

    apt_type = data.type or "visit"  # accept any string ('visit', 'call', etc.)
    apt_status = data.status if data.status in ("confirmed", "cancelled", "completed", "no_show") else "confirmed"

    user_uuid = None
    if data.user_id:
        try:
            user_uuid = _uuid.UUID(data.user_id)
        except ValueError:
            pass   # invalid UUID — ignore, create without user link

    apt = Appointment(
        user_id=user_uuid,
        property_id=data.property_id,
        start_time=start,
        end_time=end,
        type=apt_type,
        status=apt_status,
        notes=data.notes,
    )
    db.add(apt)
    db.commit()
    db.refresh(apt)

    # ── Sync with Google Calendar ────────────────────────────────────────
    _sync_create_gcal(db, apt, data, user_uuid)

    return _apt_to_dict(apt)


# ── Google Calendar sync helpers ────────────────────────────────────────────
# These bridge the sync admin endpoints with the async calendar_service.


def _sync_create_gcal(db: Session, apt, data, user_uuid) -> None:
    """Create a Google Calendar event for an admin-created appointment."""
    try:
        from app.services.calendar_service import calendar_service
        import asyncio

        if not calendar_service.is_configured:
            return

        # Get user phone
        user_phone = "Admin"
        if user_uuid:
            from app.db.models import User
            user = db.query(User).filter(User.id == user_uuid).first()
            if user:
                user_phone = user.whatsapp_phone

        # Get property title
        prop_title = "Sin propiedad"
        if data.property_id:
            prop_title = f"Propiedad {data.property_id}"
            from app.db.models import Property
            prop = db.query(Property).filter(Property.id == data.property_id).first()
            if prop:
                prop_title = prop.title or prop_title

        cal_result = asyncio.run(calendar_service.create_visit_event(
            user_phone=user_phone,
            property_id=data.property_id,
            property_title=prop_title,
            start_time=apt.start_time,
            end_time=apt.end_time,
            notes=data.notes,
        ))
        if cal_result.get("success"):
            apt.calendar_event_id = cal_result.get("event_id")
            db.commit()
            import logging
            logging.getLogger(__name__).info(
                "[Admin] Created Google Calendar event: %s", cal_result.get("event_id")
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "[Admin] Failed to sync create with Google Calendar: %s", exc
        )


def _sync_update_gcal(db: Session, apt) -> None:
    """Reschedule or create a Google Calendar event for an updated appointment."""
    try:
        from app.services.calendar_service import calendar_service
        import asyncio

        if not calendar_service.is_configured:
            return

        if apt.calendar_event_id:
            # Reschedule existing event
            cal_result = asyncio.run(calendar_service.reschedule_visit(
                event_id=apt.calendar_event_id,
                new_start_time=apt.start_time,
                new_end_time=apt.end_time,
                notes=f"Actualizado por Admin",
            ))
            if cal_result.get("success"):
                import logging
                logging.getLogger(__name__).info(
                    "[Admin] Rescheduled Google Calendar event: %s", apt.calendar_event_id
                )
        else:
            # Create new calendar event (appointment previously had no GCal link)
            user_phone = "Admin"
            if apt.user_id:
                from app.db.models import User
                user = db.query(User).filter(User.id == apt.user_id).first()
                if user:
                    user_phone = user.whatsapp_phone
            prop_title = f"Propiedad {apt.property_id}"
            from app.db.models import Property
            prop = db.query(Property).filter(Property.id == apt.property_id).first()
            if prop:
                prop_title = prop.title or prop_title
            cal_result = asyncio.run(calendar_service.create_visit_event(
                user_phone=user_phone,
                property_id=apt.property_id,
                property_title=prop_title,
                start_time=apt.start_time,
                end_time=apt.end_time,
                notes=apt.notes,
            ))
            if cal_result.get("success"):
                apt.calendar_event_id = cal_result.get("event_id")
                db.commit()
                import logging
                logging.getLogger(__name__).info(
                    "[Admin] Created Google Calendar event: %s", cal_result.get("event_id")
                )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "[Admin] Failed to sync update with Google Calendar: %s", exc
        )


def _sync_delete_gcal(db: Session, apt) -> None:
    """Cancel a Google Calendar event for a deleted/cancelled appointment."""
    if not apt.calendar_event_id:
        return
    try:
        from app.services.calendar_service import calendar_service
        import asyncio

        if not calendar_service.is_configured:
            return

        cal_result = asyncio.run(calendar_service.cancel_visit(
            event_id=apt.calendar_event_id,
            reason="Cancelada desde Admin",
        ))
        if cal_result.get("success"):
            import logging
            logging.getLogger(__name__).info(
                "[Admin] Cancelled Google Calendar event: %s", apt.calendar_event_id
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "[Admin] Failed to sync delete with Google Calendar: %s", exc
        )


@router.patch("/appointments/{apt_id}")
def update_appointment(
    apt_id: str,
    data: AppointmentUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Appointment
    from datetime import datetime, timedelta

    try:
        aid = _uuid.UUID(apt_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid appointment id (expected UUID)")

    apt = db.query(Appointment).filter(Appointment.id == aid).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    updates = data.model_dump(exclude_unset=True)

    if "start_time" in updates and updates["start_time"]:
        try:
            apt.start_time = datetime.fromisoformat(updates.pop("start_time"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid start_time format")
    elif "start_time" in updates:
        updates.pop("start_time")

    if "end_time" in updates and updates["end_time"]:
        try:
            apt.end_time = datetime.fromisoformat(updates.pop("end_time"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid end_time format")
    elif "end_time" in updates:
        updates.pop("end_time")

    if "type" in updates:
        t = updates.pop("type")
        if t:  # accept any non-empty string ('visit', 'call', etc.)
            apt.type = t

    if "status" in updates:
        s = updates.pop("status")
        if s in ("confirmed", "cancelled", "completed", "no_show"):
            apt.status = s

    if "user_id" in updates:
        uid_str = updates.pop("user_id")
        if uid_str:
            try:
                apt.user_id = _uuid.UUID(uid_str)
            except ValueError:
                pass
        else:
            apt.user_id = None

    if "property_id" in updates:
        apt.property_id = updates.pop("property_id")

    if "notes" in updates:
        apt.notes = updates.pop("notes")

    time_changed = "start_time" in updates or "end_time" in updates
    db.commit()
    db.refresh(apt)
    if time_changed:
        _sync_update_gcal(db, apt)
    return _apt_to_dict(apt)


@router.delete("/appointments/{apt_id}")
def delete_appointment(
    apt_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Appointment
    try:
        aid = _uuid.UUID(apt_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid appointment id (expected UUID)")

    apt = db.query(Appointment).filter(Appointment.id == aid).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    _sync_delete_gcal(db, apt)
    apt.status = "cancelled"
    db.commit()
    return {"status": "deleted", "appointment_id": apt_id}


# ── Google Calendar ─────────────────────────────────────────────────────────────

@router.get("/calendar/status")
def calendar_status(
    _: bool = Depends(verify_admin_api_key),
):
    """Return Google Calendar integration status and configured timezone."""
    try:
        from app.services.calendar_service import calendar_service
        configured = calendar_service.is_configured
    except Exception:
        configured = False
    return {
        "configured": configured,
        "timezone": "America/Argentina/Buenos_Aires",
        "label": "GMT-3",
    }


@router.get("/calendar/events")
def list_calendar_events(
    days_ahead: int = 30,
    max_results: int = 50,
    _: bool = Depends(verify_admin_api_key),
):
    """Fetch upcoming events from Google Calendar for the dashboard."""
    import asyncio
    try:
        from app.services.calendar_service import calendar_service
        if not calendar_service.is_configured:
            return {"configured": False, "events": [], "total": 0}
        events = asyncio.run(calendar_service.get_upcoming_events(
            days_ahead=days_ahead,
            max_results=max_results,
        ))
        return {"configured": True, "events": events, "total": len(events)}
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=traceback.format_exc())


# ── Conversations / Handoff ────────────────────────────────────────────────────

@router.get("/conversations/{phone}")
async def get_conversation(
    phone: str,
    _: bool = Depends(verify_admin_api_key),
):
    from app.core.memory import memory_manager
    try:
        context = await memory_manager.get_user_context(phone)
        if not context:
            raise HTTPException(status_code=404, detail="No conversation found")
        return {
            "phone": phone,
            "current_state": context.get("current_state"),
            "preferences": context.get("preferences", {}),
            "recent_messages": context.get("recent_messages", [])[-20:],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/handoff/{phone}")
async def handoff_to_agent(
    phone: str,
    request: HandoffRequest = HandoffRequest(),
    _: bool = Depends(verify_admin_api_key),
):
    from app.services.handoff_service import handoff_service
    try:
        result = await handoff_service.trigger_handoff(phone=phone, reason=request.reason)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Handoff failed"))
        return {"status": "handoff_completed", "phone": phone, "reason": request.reason}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AgentReply(BaseModel):
    message: str


@router.post("/reply/{phone}")
async def agent_reply(
    phone: str,
    body: AgentReply,
    _: bool = Depends(verify_admin_api_key),
):
    from app.integrations.whatsapp import whatsapp_client
    from app.api.routes.webhook import format_phone_number
    phone_to = format_phone_number(phone)
    result = await whatsapp_client.send_message(to=phone_to, message=body.message)
    if "error" in result:
        raise HTTPException(status_code=400, detail=str(result))
    return {"status": "sent", "to": phone_to}


@router.post("/users/{phone}/reset")
async def reset_user_context(
    phone: str,
    _: bool = Depends(verify_admin_api_key),
):
    """Reset conversation context for a user by phone number.
    
    Deletes all Redis keys (context, messages, summary) for the given
    phone, clears in-memory fallback caches, and resets PostgreSQL
    user preferences (location, budget, property type, lead score) to
    defaults so the next conversation starts completely fresh.
    
    Useful for testing — especially the test phone 5493754455340.
    """
    from app.core.memory import memory_manager
    try:
        success = await memory_manager.reset_user_context(phone)
        if success:
            return {
                "status": "reset",
                "phone": phone,
                "message": f"Contexto reseteado para {phone}",
            }
        return {"status": "error", "phone": phone, "message": "Reset failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume/{phone}")
async def resume_bot(
    phone: str,
    _: bool = Depends(verify_admin_api_key),
):
    from app.core.state_machine import state_machine, ConversationStateEnum
    from app.integrations.whatsapp import whatsapp_client
    from app.api.routes.webhook import format_phone_number
    await state_machine.set_state(phone, ConversationStateEnum.BROWSING.value)
    phone_to = format_phone_number(phone)
    await whatsapp_client.send_message(
        to=phone_to,
        message="El agente ha finalizado la atención. Volvés a estar en modo automático. ¿En qué más puedo ayudarte? 🏠"
    )
    return {"status": "resumed", "phone": phone}


# ── FAQ Endpoints ─────────────────────────────────────────────────────────────


class FAQCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    order: int = 0
    active: bool = True


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    order: Optional[int] = None
    active: Optional[bool] = None


def _faq_to_dict(f):
    return {
        "id": f.id,
        "question": f.question,
        "answer": f.answer,
        "category": f.category,
        "tags": f.tags or [],
        "order": f.order,
        "active": f.active,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


@router.get("/faqs")
async def list_faqs(
    category: str = None,
    search: str = None,
    active: bool = None,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Lista todas las entradas FAQ."""
    from app.db.models.faq import FAQ as FAQModel
    query = db.query(FAQModel)
    if category:
        query = query.filter(FAQModel.category == category)
    if search:
        like = f"%{search}%"
        query = query.filter(
            FAQModel.question.ilike(like) | FAQModel.answer.ilike(like)
        )
    if active is not None:
        query = query.filter(FAQModel.active == active)
    query = query.order_by(FAQModel.order.asc(), FAQModel.id.asc())
    faqs = query.all()
    return {"faqs": [_faq_to_dict(f) for f in faqs]}


@router.get("/faqs/{faq_id}")
async def get_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Obtiene una entrada FAQ por ID."""
    from app.db.models.faq import FAQ as FAQModel
    faq = db.query(FAQModel).filter(FAQModel.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return _faq_to_dict(faq)


@router.post("/faqs")
async def create_faq(
    data: FAQCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Crea una nueva entrada FAQ."""
    from app.db.models.faq import FAQ as FAQModel
    faq = FAQModel(
        question=data.question,
        answer=data.answer,
        category=data.category,
        tags=data.tags,
        order=data.order,
        active=data.active,
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return _faq_to_dict(faq)


@router.patch("/faqs/{faq_id}")
async def update_faq(
    faq_id: int,
    data: FAQUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Actualiza una entrada FAQ."""
    from app.db.models.faq import FAQ as FAQModel
    faq = db.query(FAQModel).filter(FAQModel.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(faq, key, value)
    db.commit()
    db.refresh(faq)
    return _faq_to_dict(faq)


@router.delete("/faqs/{faq_id}")
async def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Elimina una entrada FAQ."""
    from app.db.models.faq import FAQ as FAQModel
    faq = db.query(FAQModel).filter(FAQModel.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(faq)
    db.commit()
    return {"status": "deleted", "id": faq_id}


@router.get("/faqs/categories/list")
async def list_faq_categories(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Lista todas las categorías de FAQ distintas."""
    from app.db.models.faq import FAQ as FAQModel
    categories = (
        db.query(FAQModel.category)
        .filter(FAQModel.category.isnot(None))
        .distinct()
        .order_by(FAQModel.category)
        .all()
    )
    return {"categories": [c[0] for c in categories]}
