from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.repository.database import get_db
from app.core.router import router as core_router
from app.core.state_machine import state_machine
from app.utils.lang_detector import detect_language
from app.utils.logger import logger

router = APIRouter()


class WebhookVerify(BaseModel):
    mode: str
    token: str
    challenge: str


class WhatsAppMessage(BaseModel):
    from_: str
    id: str
    timestamp: str
    text: str


@router.get("/webhook")
async def verify_webhook(mode: str, token: str, challenge: str):
    from config.settings import get_settings
    settings = get_settings()
    
    if token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return challenge
    raise HTTPException(status_code=403, detail="Invalid token")


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    logger.info(f"Received webhook: {body}")
    
    entry = body.get("entry", [])
    if not entry:
        return {"status": "ok"}
    
    changes = entry[0].get("changes", [])
    if not changes:
        return {"status": "ok"}
    
    value = changes[0].get("value", {})
    messages = value.get("messages", [])
    
    if not messages:
        return {"status": "ok"}
    
    msg = messages[0]
    phone = msg.get("from")
    text = msg.get("text", {}).get("body", "")
    
    if not text:
        return {"status": "ok"}
    
    lang = detect_language(text)
    context = {
        "language": lang,
        "state": state_machine.get_state(phone).value
    }
    
    response = await core_router.route(text, phone, context)
    
    logger.info(f"Response to {phone}: {response[:100]}...")
    
    return {"status": "ok"}


@router.get("/health")
async def health_check():
    return {"status": "healthy"}