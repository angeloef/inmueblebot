from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from app.db.repository.database import get_db
from app.db.repository.repositories import LeadRepository, PropertyRepository, AppointmentRepository
from app.services.lead_service import LeadService
from app.services.property_service import PropertyService
from app.services.appointment_service import AppointmentService
from app.services.handoff_service import handoff_service
from app.core.memory import memory_manager
from app.core.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_api_key(x_api_key: str = Header(...)):
    """Simple API key verification for admin routes."""
    settings = get_settings()
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PropertyCreate(BaseModel):
    title: str
    description: Optional[str] = None
    property_type: str
    address: str
    city: str
    price: float
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area: Optional[float] = None
    featured: bool = False


class HandoffRequest(BaseModel):
    reason: Optional[str] = "user_requested"


@router.get("/leads")
def list_leads(
    min_score: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key)
):
    """List all leads with optional filtering by lead score."""
    from app.db.models.models import Lead, LeadStatus
    
    query = db.query(Lead)
    
    if min_score is not None:
        query = query.filter(Lead.lead_score >= min_score)
    
    leads = query.limit(limit).all()
    
    return {
        "leads": [
            {
                "id": l.id,
                "phone": l.phone,
                "name": l.name,
                "email": l.email,
                "status": l.status.value,
                "lead_score": l.lead_score,
                "last_interaction": l.last_interaction.isoformat() if l.last_interaction else None,
                "created_at": l.created_at.isoformat()
            }
            for l in leads
        ],
        "total": len(leads)
    }


@router.get("/leads/{lead_id}")
def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key)
):
    """Get detailed lead information."""
    from app.db.models.models import Lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {
        "id": lead.id,
        "phone": lead.phone,
        "name": lead.name,
        "email": lead.email,
        "status": lead.status.value,
        "notes": lead.notes,
        "lead_score": lead.lead_score,
        "last_interaction": lead.last_interaction.isoformat() if lead.last_interaction else None,
        "created_at": lead.created_at.isoformat()
    }


@router.patch("/leads/{lead_id}")
def update_lead(
    lead_id: int,
    data: LeadUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key)
):
    """Update lead information."""
    from app.db.models.models import Lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    repo = LeadRepository(db)
    updates = data.model_dump(exclude_unset=True)
    repo.update(lead, **updates)
    return {"status": "updated", "lead_id": lead_id}


@router.post("/properties")
def create_property(
    data: PropertyCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key)
):
    """Create a new property."""
    service = PropertyService(db)
    prop = service.create(**data.model_dump())
    return {"id": prop.id, "title": prop.title}


@router.get("/properties")
def list_properties(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key)
):
    """List all active properties."""
    from app.db.models.models import Property
    props = db.query(Property).filter(Property.active == True).all()
    return {
        "properties": [
            {
                "id": p.id,
                "title": p.title,
                "price": p.price,
                "city": p.city,
                "property_type": p.property_type,
                "bedrooms": p.bedrooms,
                "bathrooms": p.bathrooms,
                "area_m2": p.area_m2,
                "active": p.active
            }
            for p in props
        ],
        "total": len(props)
    }


@router.get("/appointments")
def list_appointments(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_admin_api_key)
):
    """List appointments with optional status filtering."""
    from app.db.models.models import Appointment, AppointmentStatus
    
    query = db.query(Appointment)
    
    if status:
        try:
            status_enum = AppointmentStatus(status)
            query = query.filter(Appointment.status == status_enum)
        except ValueError:
            pass
    
    apts = query.order_by(Appointment.scheduled_at.desc()).limit(limit).all()
    
    return {
        "appointments": [
            {
                "id": a.id,
                "lead_id": a.lead_id,
                "property_id": a.property_id,
                "scheduled_at": a.scheduled_at.isoformat(),
                "status": a.status.value,
                "created_at": a.created_at.isoformat()
            }
            for a in apts
        ],
        "total": len(apts)
    }


@router.get("/conversations/{phone}")
async def get_conversation(
    phone: str,
    _: bool = Depends(verify_admin_api_key)
):
    """Get full conversation history and context for a user."""
    try:
        context = await memory_manager.get_user_context(phone)
        
        if not context:
            raise HTTPException(status_code=404, detail="No conversation found for this phone number")
        
        return {
            "phone": phone,
            "current_state": context.get("current_state"),
            "lead_score": context.get("lead_score", 0),
            "preferences": context.get("preferences", {}),
            "recent_messages": context.get("recent_messages", [])[-20:],
            "handoff_status": context.get("preferences", {}).get("handoff_requested_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving conversation: {str(e)}")


@router.post("/handoff/{phone}")
async def handoff_to_agent(
    phone: str,
    request: HandoffRequest = HandoffRequest(),
    _: bool = Depends(verify_admin_api_key)
):
    """Trigger human handoff for a conversation."""
    try:
        result = await handoff_service.trigger_handoff(
            phone=phone,
            reason=request.reason
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Handoff failed"))
        
        return {
            "status": "handoff_completed",
            "phone": phone,
            "reason": request.reason,
            "summary": result.get("summary", "")[:500]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error initiating handoff: {str(e)}")


@router.get("/handoff/{phone}")
async def get_handoff_status(
    phone: str,
    _: bool = Depends(verify_admin_api_key)
):
    """Get handoff status for a conversation."""
    status = await handoff_service.get_handoff_status(phone)
    
    if not status:
        return {"status": "no_handoff", "phone": phone}
    
    return {"phone": phone, **status}