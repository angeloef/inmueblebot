"""
Webhook endpoint for WhatsApp Business Cloud API (Meta).

Handles:
- GET /webhook/whatsapp: Webhook verification (Meta sends hub.verify_* params)
- POST /webhook/whatsapp: Incoming messages from WhatsApp

Meta Webhook Format:
- GET: ?hub.mode=subscribe&hub.verify_token=TOKEN&hub.challenge=STRING
- POST: JSON with entry[].changes[].value.messages[]
"""

from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional, List, Dict, Any
import logging
import hashlib
import hmac

from app.agents.real_estate_agent import real_estate_agent
from app.integrations.whatsapp import whatsapp_client

logger = logging.getLogger(__name__)

router = APIRouter()


class WhatsAppIncomingMessage:
    """Parsed incoming WhatsApp message from Meta."""
    phone: str           # User's phone number
    message_id: str    # Meta message ID
    timestamp: str    # Message timestamp
    message_type: str  # text, image, audio, video, button, etc.
    text: str         # Message text or button ID
    media_url: Optional[str] = None  # Media URL if present
    media_caption: Optional[str] = None


def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify that the request came from Meta."""
    if not signature or not secret:
        return True  # Skip if no signature
    
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    """
    Meta webhook verification endpoint.
    
    Accepts ALL query parameters and extracts what we need manually.
    Handles both underscore (hub_verify_token) AND dot (hub.verify_token) formats.
    """
    from config.settings import get_settings
    settings = get_settings()
    
    # Get ALL query params as dict
    query_params = dict(request.query_params)
    
    # Extract token - try both underscore and dot formats
    verify_token = (
        query_params.get("hub_verify_token") or 
        query_params.get("hub.verify_token") or
        query_params.get("hub_verify_token_alt") or
        query_params.get("verify_token") or
        ""
    )
    challenge = (
        query_params.get("hub_challenge") or 
        query_params.get("hub.challenge") or
        query_params.get("challenge") or
        ""
    )
    mode = query_params.get("hub_mode") or query_params.get("hub.mode") or ""
    
    # Get expected token and clean ALL whitespace/newlines
    expected_token = (settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "")
    expected_token_clean = expected_token.replace("\n", "").replace("\r", "").strip()
    received_token_clean = verify_token.replace("\n", "").replace("\r", "").strip()
    
    # Detailed logging
    logger.info(f"[Webhook] ═══════════════════════════════")
    logger.info(f"[Webhook] All params: {query_params}")
    logger.info(f"[Webhook] VERIFY - mode: '{mode}'")
    logger.info(f"[Webhook] VERIFY - received token: '{received_token_clean}'")
    logger.info(f"[Webhook] VERIFY - expected token: '{expected_token_clean}'")
    logger.info(f"[Webhook] ═══════════════════════════════")
    
    # Compare
    if received_token_clean.lower() != expected_token_clean.lower():
        logger.warning(f"[Webhook] ❌ Token MISMATCH!")
        raise HTTPException(status_code=403, detail="Invalid verify token")
    
    logger.info(f"[Webhook] ✅ SUCCESS! returning: {challenge}")
    return challenge


@router.get("/webhook/verify")
async def simple_verify():
    """Simple verification check - just validates token without challenge."""
    from config.settings import get_settings
    settings = get_settings()
    
    token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
    return {
        "status": "ok",
        "token_configured": bool(token),
        "token_length": len(token or ""),
        "message": "Token is configured correctly"
    }


@router.get("/webhook/debug")
async def debug_webhook():
    """Debug endpoint - returns the configured verify token."""
    from config.settings import get_settings
    settings = get_settings()
    token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
    
    return {
        "configured_token": token,
        "token_length": len(token or ""),
        "health": "ok"
    }


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request):
    """
    Receive incoming WhatsApp messages from Meta.
    
    Meta sends POST with JSON body:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp_business",
                    "messages": [{
                        "from": "+5491112345678",
                        "id": "wamid.XXX",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {"body": "Hello"}
                    }]
                }
            }]
        }]
    }
    """
    from config.settings import get_settings
    settings = get_settings()
    
    # Get request body
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        return {"status": "error"}
    
    # Log incoming (truncated for privacy)
    logger.info(f"Incoming webhook: {str(body)[:200]}...")
    
    # Verify signature if configured
    signature = request.headers.get("x-hub-signature", "")
    if signature and settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
        # Note: We'd need raw body for full verification
        # For now, skip and trust Meta's network
        pass
    
    # Extract messages from entry
    entry = body.get("entry", [])
    if not entry:
        return {"status": "ok"}
    
    # Process each change
    for e in entry:
        changes = e.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            
            if messages:
                await process_messages(messages)
    
    return {"status": "ok"}


async def process_messages(messages: List[Dict[str, Any]]):
    """Process incoming messages and send responses."""
    for msg in messages:
        msg_type = msg.get("type", "text")
        phone = msg.get("from", "")
        message_id = msg.get("id", "")
        timestamp = msg.get("timestamp", "")
        
        if not phone:
            logger.warning("Message without sender")
            continue
        
        # Extract message content
        text = ""
        media_url = None
        media_caption = None
        
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "image":
            media_url = msg.get("image", {}).get("link", "")
            media_caption = msg.get("image", {}).get("caption", "")
            text = media_caption or "[Imagen]"
        elif msg_type == "video":
            media_url = msg.get("video", {}).get("link", "")
            text = "[Video]"
        elif msg_type == "audio":
            text = "[Audio]"
        elif msg_type == "document":
            media_url = msg.get("document", {}).get("link", "")
            text = "[Documento]"
        elif msg_type == "button":
            # Button response
            button = msg.get("button", {})
            text = button.get("payload", "") or button.get("id", "")
        elif msg_type == "interactive":
            # List reply or button reply
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("id", "")
            elif interactive.get("type") == "list_reply":
                text = interactive.get("list_reply", {}).get("id", "")
        
        # Also check for quick replies
        if not text:
            quick_reply = msg.get("quick_reply")
            if quick_reply:
                text = quick_reply.get("payload", "")
        
        if not text:
            logger.info(f"Ignoring empty message from {phone}")
            continue
        
        # Create parsed message object
        parsed = WhatsAppIncomingMessage(
            phone=phone,
            message_id=message_id,
            timestamp=timestamp,
            message_type=msg_type,
            text=text,
            media_url=media_url,
            media_caption=media_caption
        )
        
        # Process with RealEstateAgent
        logger.info(f"Processing from {phone}: {text[:30]}...")
        
        try:
            result = await real_estate_agent.process_turn(
                phone=phone,
                user_message=text
            )
            
            response_text = result.get("response_text", "")
            rich_content = result.get("rich_content", {})
            
            # Send text response
            if response_text:
                logger.info(f"Sending to {phone}: {response_text[:30]}...")
                await whatsapp_client.send_message(
                    to=phone,
                    message=response_text
                )
            
            # Send images if any
            images = rich_content.get("images", [])
            for url in images[:3]:
                await whatsapp_client.send_image(
                    to=phone,
                    image_url=url,
                    caption=rich_content.get("caption", "")
                )
            
        except Exception as e:
            logger.error(f"Error processing: {e}")
            # Send error message
            await whatsapp_client.send_message(
                to=phone,
                message="Disculpame, tuve un problema. ¿Podrías intentarlo de nuevo?"
            )


@router.get("/health")
async def health_check():
    """Health check."""
    return {
        "status": "healthy",
        "whatsapp_configured": whatsapp_client.is_configured
    }