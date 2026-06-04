from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import get_settings
from app.core.memory import MemoryManager
import uuid as _uuid
import logging

logger = logging.getLogger(__name__)

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
      14. Add conversations.session_id if missing  (cascade DELETE selects it → UndefinedColumn)
      15. Conversations 'state' drift: rename status→state (or add)  + ensure context exists
          (cascade DELETE of a user selects conversations.state → UndefinedColumn → breaks DELETE /admin/leads)
    """
    global _migration_done
    if _migration_done:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_data JSONB"
            ))
            # ── BSUID (Meta identity migration) ─────────────────────────
            # Dedicated indexed column for the Business-Scoped User ID.
            # NOTE: no backfill from extra_data here on purpose — users.extra_data
            # may be TEXT (not JSONB) in some instances, and the whole migration
            # runs in ONE transaction, so a failing backfill would roll back this
            # ADD COLUMN too. _capture_identity() repopulates bsuid per user on
            # their next inbound message.
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS bsuid VARCHAR(150)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_users_bsuid ON users (bsuid)"
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
            # ── Fix 16: Create bot_settings table ────────────────────────
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key         VARCHAR(100) PRIMARY KEY,
                    value       TEXT NOT NULL DEFAULT '',
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            # Seed default company_name if not already set
            conn.execute(text("""
                INSERT INTO bot_settings (key, value) VALUES ('company_name', 'la inmobiliaria')
                ON CONFLICT (key) DO NOTHING
            """))
            conn.execute(text("""
                INSERT INTO bot_settings (key, value) VALUES ('business_hours', 'Lunes a sábado de 9 a 18hs')
                ON CONFLICT (key) DO NOTHING
            """))
            # ── Fix 15: Create notifications table ───────────────────────
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id         SERIAL PRIMARY KEY,
                    type       VARCHAR(50) NOT NULL,
                    title      TEXT NOT NULL,
                    body       TEXT NOT NULL DEFAULT '',
                    read       BOOLEAN NOT NULL DEFAULT FALSE,
                    phone      VARCHAR(20),
                    metadata   JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_notifications_read ON notifications (read)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at DESC)"
            ))
            # ── Fix 17: Add category column to properties ─────────────────
            conn.execute(text(
                "ALTER TABLE properties ADD COLUMN IF NOT EXISTS category VARCHAR(20)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_properties_category ON properties (category)"
            ))
            # ── Fix 18: Populate category from title (best-effort) ────────
            # Order matters: terreno first (most specific), then casa, then depto, then ph
            conn.execute(text("""
                UPDATE properties SET category = 'terreno'
                WHERE category IS NULL
                  AND (title ILIKE '%terreno%' OR description ILIKE '%terreno%')
            """))
            conn.execute(text("""
                UPDATE properties SET category = 'casa'
                WHERE category IS NULL
                  AND (title ILIKE '%casa%' OR description ILIKE '%casa%')
            """))
            conn.execute(text("""
                UPDATE properties SET category = 'departamento'
                WHERE category IS NULL
                  AND (title ILIKE '%departamento%' OR title ILIKE '%depto%'
                       OR description ILIKE '%departamento%')
            """))
            conn.execute(text("""
                UPDATE properties SET category = 'ph'
                WHERE category IS NULL
                  AND (title ILIKE '%ph %' OR title ILIKE '% ph%'
                       OR title ILIKE '%p.h.%' OR description ILIKE '%ph %')
            """))
            # ── Fix 14: Add session_id to conversations if missing ───────
            # The Conversation model defines session_id as NOT NULL, but older
            # DB instances (pre-migration) don't have this column.
            # SQLAlchemy SELECTs it on every cascade DELETE → UndefinedColumn error.
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'conversations' AND column_name = 'session_id'
                    ) THEN
                        ALTER TABLE conversations
                            ADD COLUMN session_id VARCHAR(100) NOT NULL DEFAULT 'legacy';
                        CREATE INDEX IF NOT EXISTS ix_conversations_session_id
                            ON conversations (session_id);
                    END IF;
                END $$;
            """))
            # ── Fix 15: Conversation 'state' column drift ────────────────
            # Same class as Fix 14: the cascade DELETE of a user SELECTs
            # conversations.state, but older DBs have the column named 'status'
            # → UndefinedColumn error (breaks DELETE /admin/leads/{id}).
            # Rename status→state (or add state if neither exists). Also ensure
            # 'context' exists, since the same cascade SELECT reads it.
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'conversations' AND column_name = 'state'
                    ) THEN
                        IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'conversations' AND column_name = 'status'
                        ) THEN
                            ALTER TABLE conversations RENAME COLUMN status TO state;
                        ELSE
                            ALTER TABLE conversations
                                ADD COLUMN state VARCHAR(30) NOT NULL DEFAULT 'idle';
                        END IF;
                    END IF;
                END $$;
            """))
            conn.execute(text(
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS context JSONB"
            ))
            # ── Fix 19: Make whatsapp_phone nullable for BSUID-only users ──────
            try:
                conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN whatsapp_phone DROP NOT NULL"
                ))
                logger.info("Migration Fix 19: whatsapp_phone set nullable")
            except Exception as e:
                logger.warning(f"Migration Fix 19 (whatsapp_phone nullable): {e}")

            # ── Fix 20: Drop unique constraint on whatsapp_phone ───────────────
            try:
                conn.execute(text(
                    "ALTER TABLE users DROP CONSTRAINT IF EXISTS users_whatsapp_phone_key"
                ))
                logger.info("Migration Fix 20: whatsapp_phone unique constraint dropped")
            except Exception as e:
                logger.warning(f"Migration Fix 20 (drop unique): {e}")

            # ── Fix 21: Add sender column to messages table ───────────────────
            try:
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender VARCHAR(20) NOT NULL DEFAULT 'user'"
                ))
                logger.info("Migration Fix 21: messages.sender added")
            except Exception as e:
                logger.warning(f"Migration Fix 21: {e}")

            # ── Fix 22: Add msg_metadata column to messages table ─────────────
            try:
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS msg_metadata JSONB"
                ))
                logger.info("Migration Fix 22: messages.msg_metadata added")
            except Exception as e:
                logger.warning(f"Migration Fix 22: {e}")

            # ── Fix 23: Add bot_paused column to conversations table ──────────
            try:
                conn.execute(text(
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS bot_paused BOOLEAN NOT NULL DEFAULT FALSE"
                ))
                logger.info("Migration Fix 23: conversations.bot_paused added")
            except Exception as e:
                logger.warning(f"Migration Fix 23: {e}")

            # ── Fix 24: Add last_message_at column to conversations table ─────
            try:
                conn.execute(text(
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ"
                ))
                logger.info("Migration Fix 24: conversations.last_message_at added")
            except Exception as e:
                logger.warning(f"Migration Fix 24: {e}")

            # ── Fix 25: Add media_url column to messages table ───────────────
            try:
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_url VARCHAR(500)"
                ))
                logger.info("Migration Fix 25: messages.media_url added")
            except Exception as e:
                logger.warning(f"Migration Fix 25: {e}")

            # ── Fix 26: Ensure all core message columns exist ──────────────
            try:
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
                    "timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                ))
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS content TEXT"
                ))
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS role "
                    "VARCHAR(20) NOT NULL DEFAULT 'user'"
                ))
                conn.execute(text(
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS "
                    "conversation_id UUID"
                ))
                # Ensure auto-increment sequence on messages.id
                conn.execute(text(
                    "CREATE SEQUENCE IF NOT EXISTS messages_id_seq"
                ))
                conn.execute(text(
                    "ALTER TABLE messages ALTER COLUMN id "
                    "SET DEFAULT nextval('messages_id_seq')"
                ))
                conn.execute(text(
                    "SELECT setval('messages_id_seq', "
                    "COALESCE((SELECT MAX(id) FROM messages), 1))"
                ))
                logger.info("Migration Fix 26: messages core columns ensured")
            except Exception as e:
                logger.warning(f"Migration Fix 26: {e}")

            # NOTE: Las tablas de Cobranzas se crean en una transacción AISLADA en
            # app/api/routes/cobranzas.py (ensure_cobranzas_schema), no acá: esta
            # migración corre como UNA sola transacción y, si una sentencia previa
            # aborta, el commit final haría rollback de todo (incl. esas tablas).

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
        # Phase 0a: gateado. Alembic es la autoridad de DDL una vez aplicado el baseline;
        # hasta entonces, las migraciones imperativas legacy siguen corriendo.
        if get_settings().RUN_LEGACY_STARTUP_MIGRATION:
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
def debug_users(
    _: bool = Depends(verify_admin_api_key),
):
    """Diagnóstico: ejecuta query de users y retorna info básica. Requiere auth."""
    try:
        db = _get_sync_session()
        from sqlalchemy import text as _text
        result = db.execute(_text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [r[0] for r in result.fetchall()]
        try:
            from app.db.models import User
            user_count = db.query(User).count()
            return {"tables": tables, "user_count": user_count}
        except Exception:
            return {"tables": tables, "user_error": "Query failed"}
        finally:
            db.close()
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


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
    zone: Optional[str] = None             # Zone/barrio → Property.extra_data['zone']
    price: Optional[int] = 0              # Property.price (integer cents/USD)
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_m2: Optional[int] = None
    currency: str = "ARS"
    status: str = "available"             # 'available','reserved','sold','rented'
    images: Optional[List[str]] = None    # List of image URLs
    category: Optional[str] = None        # 'casa', 'departamento', 'ph', 'terreno' → Property.category


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


class PropertyStatusUpdate(BaseModel):
    """Quick status change — only the status field."""
    status: str = "available"  # 'available','reserved','sold','rented'


class PropertyRelateClient(BaseModel):
    """Link a client to a property with a relationship type."""
    client_id: str            # UUID of the User/Lead
    relation: str = "interested"  # 'interested', 'buyer', 'tenant'
    update_status: bool = True    # auto-update property status


class ClientPropertyInterest(BaseModel):
    """Toggle a client's interest in a property."""
    property_id: int
    interested: bool = True   # True = add interest, False = remove


# ── Serialization helpers ──────────────────────────────────────────────────────

_ROLE_TO_STATUS = {"prospect": "new", "tenant": "converted", "owner": "new", "lost": "lost"}


def _parse_extra(raw) -> dict:
    """Normaliza extra_data: acepta dict, str JSON, o None."""
    import json as _json
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _user_to_dict(u):
    """Serializa User al shape que espera el dashboard (compatible con toClient())."""
    extra = _parse_extra(getattr(u, 'extra_data', None))
    role = extra.get("role", "prospect")
    return {
        "id": str(u.id),
        "phone": u.whatsapp_phone or u.bsuid or "N/A",
        "bsuid": u.bsuid,
        "name": u.name,
        "email": extra.get("email"),
        "role": role,                                      # raw role, no round-trip loss
        "status": _ROLE_TO_STATUS.get(role, "new"),        # backward compat
        "notes": extra.get("notes"),
        "tags": [],
        "property_relations": extra.get("property_relations", []),
        "lead_score": getattr(u, 'lead_score', 0) or 0,
        "last_interaction": u.last_interaction.isoformat() if u.last_interaction else None,
        "updated_at": u.last_interaction.isoformat() if u.last_interaction else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _prop_to_dict(p):
    """Serializa Property al shape que espera el dashboard (compatible con toProperty())."""
    extra = p.extra_data or {}
    city = extra.get("city", "")
    zone = extra.get("zone", "")
    street = extra.get("street", "")
    
    # If extra_data has structured fields, use them. Otherwise fall back to parsing location.
    if street and zone:
        address = street
        neigh = zone
        display_city = city
    elif p.location:
        parts = [x.strip() for x in p.location.split(",")]
        address = parts[0] if parts else p.location
        neigh = parts[1] if len(parts) > 1 else ""
        display_city = parts[2] + ", " + parts[3] if len(parts) >= 4 else (", ".join(parts[1:]) if len(parts) > 1 else "")
    else:
        address = ""
        neigh = ""
        display_city = ""
    
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description,
        "category": p.category or "",
        "property_type": p.category or extra.get("building_type", ""),
        "address": address,                                   # street only
        "city": display_city,                                 # city for display
        "neigh": neigh,                                       # zone/barrio
        "price": p.price,
        "bedrooms": p.bedrooms,
        "bathrooms": p.bathrooms,
        "area": p.area_m2,                                 # toProperty() reads area/area_m2
        "images": p.images or [],
        "featured": False,
        "active": p.status in ("available", "reserved"),
        "status": p.status,
        "type": p.type,                                    # 'venta' or 'alquiler'
        "currency": getattr(p, "currency", "ARS") or "ARS",
        "buyer_id": extra.get("buyer_id"),
        "tenant_id": extra.get("tenant_id"),
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
    limit: int = 500,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import User
    from sqlalchemy import func as _func
    try:
        users = db.query(User).order_by(User.created_at.desc().nullslast()).limit(limit).all()
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
    extra = {
        "email": data.email,
        "role": data.role or "prospect",
        "notes": data.notes,
    }
    user = User(whatsapp_phone=data.phone or None, name=data.name)
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
    extra = dict(_parse_extra(getattr(user, 'extra_data', None)))
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
async def reset_user_context(
    phone: str,
    _: bool = Depends(verify_admin_api_key),
):
    """Reset conversation context for a user by phone number.
    Clears Redis keys, in-memory fallback, and PostgreSQL preferences.
    Useful for testing — ensures the bot starts fresh on next message."""
    from app.core.memory import memory_manager as _mm
    try:
        success = await _mm.reset_user_context(phone)
        return {"status": "reset" if success else "error", "phone": phone}
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
    props = db.query(Property).order_by(Property.created_at.desc().nullslast()).all()
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

    # Build extra_data with structured fields
    extra_data_dict = {"building_type": data.building_type, "city": data.city or ""}

    # Store zone: explicit field first, then try to extract from location string
    if data.zone:
        extra_data_dict["zone"] = data.zone
    elif location and ", " in location:
        # Extract zone from location string: "Av. Cabildo 2350, Centro" → zone="Centro"
        _loc_parts = location.split(", ", 1)
        if len(_loc_parts) > 1 and _loc_parts[1].strip():
            extra_data_dict["zone"] = _loc_parts[1].strip()

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
        category=data.category,
        extra_data=extra_data_dict,
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
        # Keep extra_data['street'] in sync — _prop_to_dict() prefers the structured
        # 'street' field over parsing location, so a stale street would silently
        # revert the edited address on refetch.
        extra = dict(prop.extra_data or {})
        extra["street"] = prop.location.split(",")[0].strip() if prop.location else ""
        prop.extra_data = extra
    if "area_m2" in updates:
        prop.area_m2 = updates.pop("area_m2")
    if "status" in updates:
        s = updates.pop("status")
        prop.status = s if s in ("available", "reserved", "sold", "rented") else "available"
    if "category" in updates:
        cat = updates.pop("category")
        prop.category = cat if cat in ("casa", "departamento", "ph", "terreno") else None
    if "building_type" in updates:
        extra = dict(prop.extra_data or {})
        extra["building_type"] = updates.pop("building_type")
        prop.extra_data = extra
    if "city" in updates:
        extra = dict(prop.extra_data or {})
        extra["city"] = updates.pop("city")
        prop.extra_data = extra
    if "zone" in updates:
        extra = dict(prop.extra_data or {})
        extra["zone"] = updates.pop("zone")
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
    from app.db.models import Property, Appointment
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    # Hard delete — the dashboard's delete button promises permanent removal.
    # (A 'sold' status is set separately via the status dropdown / buyer assignment.)
    # Remove dependent appointments first: the FK is ON DELETE CASCADE in the model,
    # but delete explicitly so this works even if the live constraint lacks it.
    db.query(Appointment).filter(Appointment.property_id == prop_id).delete(synchronize_session=False)
    db.delete(prop)
    db.commit()
    return {"status": "deleted", "property_id": prop_id}


# ── Quick Status Change ─────────────────────────────────────────────────────────

@router.patch("/properties/{prop_id}/status")
def update_property_status(
    prop_id: int,
    data: PropertyStatusUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Quick status update without full property edit."""
    from app.db.models import Property
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    valid = ("available", "reserved", "sold", "rented")
    if data.status not in valid:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of {valid}")
    prop.status = data.status
    db.commit()
    return {"status": "updated", "property_id": prop_id, "new_status": prop.status}


# ── Client-Property Relationship ────────────────────────────────────────────────

@router.post("/properties/{prop_id}/relate-client")
def relate_client_to_property(
    prop_id: int,
    data: PropertyRelateClient,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Link a client to a property with a relationship type. Optionally updates property status.

    Relations:
      - 'interested': marks client as interested (adds to property_relations on client)
      - 'buyer': marks client as buyer, sets property status → 'sold'
      - 'tenant': marks client as tenant, sets property status → 'rented'
    """
    from app.db.models import User, Property
    from uuid import UUID as _UUID

    # Validate client
    try:
        uid = _UUID(data.client_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid client_id format (expected UUID)")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")

    # Validate property
    prop = db.query(Property).filter(Property.id == prop_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Update property extra_data with buyer/tenant ID
    extra = dict(prop.extra_data or {})
    if data.relation == "none":
        # Unlink: remove buyer/tenant references
        extra.pop("buyer_id", None)
        extra.pop("tenant_id", None)
        # Don't change status on unlink
    elif data.relation == "buyer":
        extra["buyer_id"] = data.client_id
        if data.update_status:
            prop.status = "sold"
    elif data.relation == "tenant":
        extra["tenant_id"] = data.client_id
        if data.update_status:
            prop.status = "rented"
    prop.extra_data = extra
    db.flush()

    # Update user extra_data with property_relations
    uextra = _parse_extra(getattr(user, 'extra_data', None))
    relations = uextra.get("property_relations", [])

    if data.relation == "none":
        # Unlink: remove relation, reset role to prospect if no other relations
        relations = [r for r in relations if r.get("prop_id") != prop_id]
        uextra["property_relations"] = relations
        if not relations:
            uextra["role"] = "prospect"
    else:
        # Update client role when linking as buyer or tenant
        if data.relation == "buyer":
            uextra["role"] = "owner"
        elif data.relation == "tenant":
            uextra["role"] = "tenant"

        # Remove existing relation for this property if any
        relations = [r for r in relations if r.get("prop_id") != prop_id]
        from datetime import datetime as _dt
        relations.append({
            "prop_id": prop_id,
            "relation": data.relation,
            "date": _dt.utcnow().isoformat(),
        })
        uextra["property_relations"] = relations
    try:
        user.extra_data = uextra
    except AttributeError:
        pass

    db.commit()
    return {
        "status": "linked",
        "property_id": prop_id,
        "client_id": data.client_id,
        "relation": data.relation,
        "property_status": prop.status,
    }


@router.patch("/leads/{lead_id}/property-interest")
def toggle_client_property_interest(
    lead_id: str,
    data: ClientPropertyInterest,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Toggle a client's interest in a property."""
    from app.db.models import User
    try:
        uid = _uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid lead_id format (expected UUID)")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="Lead not found")

    uextra = _parse_extra(getattr(user, 'extra_data', None))
    relations = uextra.get("property_relations", [])
    if data.interested:
        # Add interest if not already present
        exists = any(r.get("prop_id") == data.property_id for r in relations)
        if not exists:
            from datetime import datetime as _dt
            relations.append({
                "prop_id": data.property_id,
                "relation": "interested",
                "date": _dt.utcnow().isoformat(),
            })
    else:
        # Remove interest
        relations = [r for r in relations if r.get("prop_id") != data.property_id]

    uextra["property_relations"] = relations
    try:
        user.extra_data = uextra
    except AttributeError:
        pass
    db.commit()
    return {"status": "updated", "lead_id": lead_id, "property_id": data.property_id, "interested": data.interested}


# ── Appointments ───────────────────────────────────────────────────────────────

@router.get("/appointments")
def list_appointments(
    status: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    from app.db.models import Appointment
    query = db.query(Appointment)
    if status:
        query = query.filter(Appointment.status == status)
    apts = query.order_by(Appointment.start_time.desc()).limit(limit).all()
    return {"appointments": [_apt_to_dict(a) for a in apts], "total": len(apts)}


@router.get("/appointments/{apt_id}")
def get_appointment(
    apt_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Obtiene un appointment por UUID — usado por el dashboard para abrir el modal desde notificación."""
    from app.db.models import Appointment
    import uuid as _uuid
    try:
        apt_uuid = _uuid.UUID(apt_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    apt = db.query(Appointment).filter(Appointment.id == apt_uuid).first()
    if not apt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _apt_to_dict(apt)


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
                user_phone = user.whatsapp_phone or user.bsuid or "Unknown"

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
                    user_phone = user.whatsapp_phone or user.bsuid or "Unknown"
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
    time_changed = "start_time" in updates or "end_time" in updates

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
    db.delete(apt)
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

@router.get("/conversations/by-phone/{phone}")
async def get_conversation_by_phone(
    phone: str,
    _: bool = Depends(verify_admin_api_key),
):
    """(Legacy) Look up conversation context by phone number.
    Prefer /admin/conversations/{id} for inbox integration."""
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


class SimulateRequest(BaseModel):
    """Request body for the simulate endpoint (massive testing without WhatsApp)."""
    phone: str
    message: str
    reset: bool = False
    """If True, resets user context before processing (fresh conversation)."""


@router.post("/simulate")
async def simulate_conversation_turn(
    body: SimulateRequest,
    _: bool = Depends(verify_admin_api_key),
):
    """
    Simula un turno de conversación SIN enviar a WhatsApp.
    
    Procesa el mensaje exactamente como lo haría el webhook de WhatsApp,
    pero devuelve la respuesta completa del agente en lugar de enviarla
    por WhatsApp. Ideal para tests masivos automatizados.

    Args:
        phone: Número de teléfono del usuario simulado
        message: Mensaje del usuario
        reset: Si True, resetea el contexto del usuario antes de procesar

    Returns:
        response_text: Texto de respuesta del bot
        tools_used: Lista de herramientas ejecutadas
        rich_content: Contenido adicional (propiedades, imágenes)
        next_state: Estado siguiente del state machine
        timing: Tiempos de procesamiento
    """
    from app.agents.real_estate_agent import real_estate_agent
    from app.core.config import get_settings
    settings = get_settings()
    import time

    phone = body.phone
    message = body.message

    # Opcional: resetear contexto para empezar conversación fresca
    if body.reset:
        try:
            await memory_manager.reset_user_context(phone)
            logger.info(f"[Simulate] Context reset for {phone}")
        except Exception as e:
            logger.warning(f"[Simulate] Context reset failed: {e}")

    start_time = time.time()

    try:
        # ── v2.0 Router Feature Flag ──────────────────────────────────
        # Check bot_settings DB first, fall back to env var
        use_v2 = settings.USE_V2_ROUTER
        try:
            from app.agents.prompts import _get_cached_bot_settings
            bot_cfg = _get_cached_bot_settings()
            db_val = (bot_cfg or {}).get("use_v2_router", "")
            if db_val == "true":
                use_v2 = True
            elif db_val == "false":
                use_v2 = False
        except Exception:
            pass

        if use_v2:
            from app.routers.v2_adapter import process_turn_v2
            result = await process_turn_v2(
                phone=phone,
                user_message=message,
            )
        else:
            result = await real_estate_agent.process_turn(
                phone=phone,
                user_message=message,
            )
    except Exception as e:
        logger.error(f"[Simulate] process_turn failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - start_time

    # Apply same sanitization as webhook (strip CONFIRMED tags, base64, etc.)
    from app.utils.sanitizer import sanitize_bot_response as _sanitize
    response_text = _sanitize(result.get("response_text", ""))
    tools_used = result.get("tools_used", [])
    rich_content = result.get("rich_content")
    next_state = result.get("next_state", "")

    return {
        "response_text": response_text,
        "tools_used": tools_used,
        "rich_content": rich_content,
        "next_state": next_state,
        "timing": {"turn_seconds": round(elapsed, 3)},
    }


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


# ── Notifications ─────────────────────────────────────────────────────────────

def _notif_to_dict(row) -> dict:
    return {
        "id":         row.id,
        "type":       row.type,
        "title":      row.title,
        "body":       row.body,
        "read":       row.read,
        "phone":      row.phone,
        "metadata":   row.metadata or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/notifications")
def list_notifications(
    unread: bool = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Lista notificaciones. ?unread=true filtra solo no leídas."""
    from sqlalchemy import text as _t
    query = "SELECT * FROM notifications"
    params = {}
    if unread is True:
        query += " WHERE read = FALSE"
    elif unread is False:
        query += " WHERE read = TRUE"
    query += " ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit
    rows = db.execute(_t(query), params).fetchall()
    unread_count = db.execute(_t("SELECT COUNT(*) FROM notifications WHERE read = FALSE")).scalar()
    return {
        "notifications": [_notif_to_dict(r) for r in rows],
        "unread_count": unread_count,
        "total": len(rows),
    }


@router.patch("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Marca una notificación como leída."""
    from sqlalchemy import text as _t
    result = db.execute(
        _t("UPDATE notifications SET read = TRUE WHERE id = :id"),
        {"id": notif_id}
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok", "id": notif_id}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Marca todas las notificaciones como leídas."""
    from sqlalchemy import text as _t
    db.execute(_t("UPDATE notifications SET read = TRUE WHERE read = FALSE"))
    db.commit()
    return {"status": "ok"}


@router.delete("/notifications/{notif_id}")
def delete_notification(
    notif_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Elimina una notificación."""
    from sqlalchemy import text as _t
    result = db.execute(
        _t("DELETE FROM notifications WHERE id = :id"),
        {"id": notif_id}
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "deleted", "id": notif_id}


@router.post("/notifications/delete-read")
def delete_read_notifications(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Elimina todas las notificaciones ya leídas."""
    from sqlalchemy import text as _t
    result = db.execute(_t("DELETE FROM notifications WHERE read = TRUE"))
    db.commit()
    return {"status": "deleted", "count": result.rowcount}


# ── Bot Settings ──────────────────────────────────────────────────────────────

# All bot-operational settings are stored as key-value rows in bot_settings.
# The dashboard Config page reads/writes via these endpoints.
# The bot reads them via get_bot_setting() with an in-memory 5-min cache.

_ALLOWED_SETTINGS = {
    "company_name":         "Nombre de la inmobiliaria",
    "business_hours":       "Horario de atención",
    "agent_whatsapp":       "WhatsApp del agente humano (handoffs)",
    "use_v2_router":        "Activar router v2 (ChatbotSerio S1+S2). true/false (legacy)",
    "active_router":        "Router activo: v1 | v2 | v3 (V3 Phase 1.5). Supersede a use_v2_router.",
}


class BotSettingsUpdate(BaseModel):
    company_name:     Optional[str] = None
    business_hours:   Optional[str] = None
    agent_whatsapp:   Optional[str] = None
    use_v2_router:    Optional[str] = None  # "true" / "false" (legacy)
    active_router:    Optional[str] = None  # "v1" | "v2" | "v3"


@router.get("/settings")
def get_bot_settings(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Devuelve todos los bot_settings como un dict plano {key: value}."""
    from sqlalchemy import text as _t
    rows = db.execute(_t("SELECT key, value FROM bot_settings")).fetchall()
    result = {r[0]: r[1] for r in rows}
    # Fill in defaults for allowed keys not yet in DB
    for key in _ALLOWED_SETTINGS:
        result.setdefault(key, "")
    return result


@router.patch("/settings")
def update_bot_settings(
    data: BotSettingsUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Actualiza uno o más bot_settings. Solo acepta campos de _ALLOWED_SETTINGS."""
    from sqlalchemy import text as _t
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return {"status": "no_changes"}
    for key, value in updates.items():
        if key not in _ALLOWED_SETTINGS:
            continue
        db.execute(_t("""
            INSERT INTO bot_settings (key, value, updated_at)
            VALUES (:key, :value, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """), {"key": key, "value": value or ""})
    db.commit()
    # Bust the in-memory cache in prompts.py so bot picks up changes immediately
    try:
        from app.agents.prompts import _bust_settings_cache
        _bust_settings_cache()
    except Exception:
        pass
    return {"status": "updated", "keys": list(updates.keys())}


# ── WhatsApp Inbox — Conversations (Admin API) ──────────────────────────

import uuid as _uuid
import asyncio
import json


class ConversationReply(BaseModel):
    text: str


def _make_async_session():
    """Create and return an async SQLAlchemy session for admin endpoints."""
    # Ensure the startup migration runs before any async query touches the DB
    _get_sync_session()
    from app.db.session import async_session_factory
    return async_session_factory()


@router.get("/conversations")
async def admin_list_conversations(
    limit: int = 50,
    offset: int = 0,
    _: bool = Depends(verify_admin_api_key),
):
    """List all conversations, sorted by last_message_at DESC."""
    from app.services.conversation_service import list_conversations as _list
    async with _make_async_session() as db:
        conversations = await _list(db, limit=limit, offset=offset)
    return {"conversations": conversations, "total": len(conversations)}


@router.get("/conversations/{conversation_id}")
async def admin_get_conversation(
    conversation_id: str,
    _: bool = Depends(verify_admin_api_key),
):
    """Get conversation detail with all messages."""
    from app.services.conversation_service import get_conversation as _get
    async with _make_async_session() as db:
        conv = await _get(db, _uuid.UUID(conversation_id))
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("/conversations/{conversation_id}/reply")
async def admin_reply_to_conversation(
    conversation_id: str,
    body: ConversationReply,
    _: bool = Depends(verify_admin_api_key),
):
    """Admin replies to a conversation — sends WhatsApp message + persists."""
    from app.core.identity import set_current_contact
    from app.integrations.whatsapp import whatsapp_client
    from app.services.conversation_service import (
        get_user_phone_for_conversation,
        save_admin_message,
    )

    conv_uuid = _uuid.UUID(conversation_id)

    async with _make_async_session() as db:
        # Get user phone
        user_phone = await get_user_phone_for_conversation(db, conv_uuid)
        if not user_phone:
            raise HTTPException(status_code=404, detail="User not found for this conversation")

        # Normalize phone for Meta API (same as webhook does)
        from app.api.routes.webhook import format_phone_number
        phone_to = format_phone_number(user_phone)

        # Set identity with the RAW phone (with +) so _post_message fallback works
        raw_phone = user_phone if user_phone.startswith('+') else f'+{user_phone}'
        set_current_contact(phone=raw_phone, bsuid=None)

        whatsapp_result = None
        whatsapp_error = None
        try:
            whatsapp_result = await whatsapp_client.send_message(to=phone_to, message=body.text)
            if isinstance(whatsapp_result, dict) and whatsapp_result.get("error"):
                whatsapp_error = whatsapp_result.get("error")
        except Exception as e:
            whatsapp_error = str(e)

        # Save admin message (even if WhatsApp send fails)
        saved = await save_admin_message(db, conv_uuid, body.text)

    result = {
        "message_id": saved["id"],
        "sent_at": saved["timestamp"],
    }
    if whatsapp_result and not whatsapp_error:
        msg_id = (whatsapp_result.get("messages") or [{}])[0].get("id", "")
        result["whatsapp_message_id"] = msg_id
    if whatsapp_error:
        result["whatsapp_error"] = whatsapp_error

    return result


@router.patch("/conversations/{conversation_id}/toggle-bot")
async def admin_toggle_bot(
    conversation_id: str,
    _: bool = Depends(verify_admin_api_key),
):
    """Toggle bot_paused on a conversation."""
    from app.services.conversation_service import toggle_bot as _toggle
    async with _make_async_session() as db:
        try:
            result = await _toggle(db, _uuid.UUID(conversation_id))
        except ValueError:
            raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.get("/conversations/{conversation_id}/stream")
async def admin_conversation_stream(
    conversation_id: str,
    token: str = "",
    x_api_key: str = Header(None, alias="x-api-key"),
):
    """SSE stream for real-time conversation updates.

    Accepts API key via ?token= query parameter (for EventSource compatibility
    in the browser) or via x-api-key header.
    """
    from app.services.conversation_service import subscribe, unsubscribe

    # Validate API key — accept header OR query param
    settings = get_settings()
    api_key = x_api_key or token
    if not api_key or api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    q = subscribe(conversation_id)

    async def event_generator():
        try:
            while True:
                try:
                    # Wait for event with 30s timeout for keepalive
                    data = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(conversation_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Data cleanup ───────────────────────────────────────────────────────

CLIENT_TABLES = [
    "appointments",
    "conversations",
    "messages",
    "user_episodes",
    "users",
]


@router.post("/cleanup-clients")
async def cleanup_clients(
    confirm: str = "",
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key),
):
    """Delete ALL client data. Requires ?confirm=yes."""
    if confirm != "yes":
        counts = {}
        for table in CLIENT_TABLES:
            r = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = r.scalar()
        return {
            "status": "preview",
            "message": "Add ?confirm=yes to actually delete",
            "tables": counts,
        }
    results = {}
    for table in CLIENT_TABLES:
        r = db.execute(text(f"DELETE FROM {table}"))
        results[table] = r.rowcount
    db.commit()
    return {
        "status": "deleted",
        "tables": results,
    }
