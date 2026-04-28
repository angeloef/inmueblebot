from typing import Optional
from sqlalchemy.orm import Session
from app.db.models.models import Lead, LeadStatus
from app.db.repository.repositories import LeadRepository


class LeadService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = LeadRepository(db)

    def get_or_create(self, phone: str, name: Optional[str] = None) -> Lead:
        lead = self.repo.get_by_phone(phone)
        if not lead:
            lead = self.repo.create(phone=phone, name=name)
        return lead

    def update_status(self, phone: str, status: LeadStatus) -> Optional[Lead]:
        lead = self.repo.get_by_phone(phone)
        if lead:
            return self.repo.update(lead, status=status.value)
        return None

    def update_contact_info(self, phone: str, name: Optional[str] = None, email: Optional[str] = None) -> Optional[Lead]:
        lead = self.repo.get_by_phone(phone)
        if lead:
            updates = {}
            if name:
                updates["name"] = name
            if email:
                updates["email"] = email
            return self.repo.update(lead, **updates) if updates else lead
        return None

    def list_leads(self, status: Optional[LeadStatus] = None, limit: int = 100):
        return self.repo.list_(status=status, limit=limit)