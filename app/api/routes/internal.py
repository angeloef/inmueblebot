from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.repository.database import get_db

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/sync-properties")
def sync_properties(db: Session = Depends(get_db)):
    return {"status": "synced", "count": 0}


@router.post("/cleanup-sessions")
def cleanup_sessions():
    from app.core.state_machine import state_machine
    return {"status": "cleaned"}


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    from app.db.models.models import Lead, Property, Appointment
    
    leads_count = db.query(Lead).count()
    properties_count = db.query(Property).count()
    appointments_count = db.query(Appointment).count()
    
    return {
        "leads": leads_count,
        "properties": properties_count,
        "appointments": appointments_count
    }