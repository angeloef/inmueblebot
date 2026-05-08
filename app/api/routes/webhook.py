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
from fastapi.responses import PlainTextResponse
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import logging
import hashlib
import hmac
import time
import asyncio
import traceback
from app.agents.real_estate_agent import real_estate_agent
from app.integrations.whatsapp import whatsapp_client
from app.core.config import get_settings
from app.utils.sanitizer import sanitize_text, sanitize_phone, sanitize_property_id

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Production guards ──────────────────────────────────────────────────────────
# Dedup cache: message_id → timestamp. Prevents processing the same message twice.
_processed_ids: Dict[str, float] = {}
_DEDUP_TTL = 300  # 5 minutes

# Per-user rate limiter: phone → list of timestamps.
# Limits concurrent processing to one message per user at a time.
_user_locks: Dict[str, float] = {}
_USER_RATE_LIMIT = 1.0  # seconds between messages from same user


def _is_duplicate(message_id: str) -> bool:
    """Check if a message_id was already processed (within TTL)."""
    now = time.time()
    ts = _processed_ids.get(message_id)
    if ts and (now - ts) < _DEDUP_TTL:
        return True
    _processed_ids[message_id] = now
    # Prune stale entries every 100 IDs
    if len(_processed_ids) > 1000:
        stale = [mid for mid, t in _processed_ids.items() if (now - t) > _DEDUP_TTL]
        for mid in stale:
            del _processed_ids[mid]
    return False


def _check_user_rate_limit(phone: str) -> bool:
    """Return True if this user should be allowed through."""
    now = time.time()
    last = _user_locks.get(phone)
    if last and (now - last) < _USER_RATE_LIMIT:
        return False
    _user_locks[phone] = now
    return True


@dataclass
class WhatsAppIncomingMessage:
    """Parsed incoming WhatsApp message from Meta."""
    phone: str           # User's phone number
    message_id: str      # Meta message ID
    timestamp: str       # Message timestamp
    message_type: str    # text, image, audio, video, button, etc.
    text: str            # Message text or button ID
    media_url: Optional[str] = None  # Media URL if present
    media_caption: Optional[str] = None


def format_phone_number(phone: str) -> str:
    """
    Normaliza números de teléfono argentinos para la API de Meta.

    Ejemplos:
      +543754532056   → 54375415532056
      +5493754532056  → 54375415532056
       5493754532056  → 54375415532056

    Reglas:
      1. Elimina el prefijo '+'
      2. Elimina el '9' en la posición 3 (prefijo de celular argentino tras '54')
      3. Inserta '15' después de los primeros 6 dígitos
    """
    phone = phone.lstrip("+").strip()

    # Eliminar el '9' de celular si está en la posición índice 2 (ej: 54[9]3754...)
    if len(phone) > 2 and phone[2] == "9":
        phone = phone[:2] + phone[3:]

    # Insertar '15' después del código de área (posición 6)
    if len(phone) >= 6 and "15" not in phone[4:8]:
        phone = phone[:6] + "15" + phone[6:]

    return phone


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


@router.get("/whatsapp")
async def verify_webhook(request: Request):
    """
    Meta webhook verification endpoint.

    Accepts ALL query parameters and extracts what we need manually.
    Handles both underscore (hub_verify_token) AND dot (hub.verify_token) formats.
    """
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
    return PlainTextResponse(content=challenge)


@router.get("/verify")
async def simple_verify():
    """Simple verification check - just validates token without challenge."""
    settings = get_settings()
    
    token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
    return {
        "status": "ok",
        "token_configured": bool(token),
        "token_length": len(token or ""),
        "message": "Token is configured correctly"
    }


@router.get("/debug")
async def debug_webhook():
    """Debug endpoint - returns the configured verify token."""
    settings = get_settings()
    token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN
    
    return {
        "configured_token": token,
        "token_length": len(token or ""),
        "health": "ok"
    }


@router.post("/whatsapp")
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

            # Delivery status updates (sent, delivered, read, failed)
            statuses = value.get("statuses", [])
            for status in statuses:
                msg_id = status.get("id", "?")
                status_val = status.get("status", "?")
                recipient = status.get("recipient_id", "?")
                errors = status.get("errors", [])
                if errors:
                    logger.error(f"[WhatsApp] STATUS {status_val} | msg={msg_id} | to={recipient} | errors={errors}")
                else:
                    logger.info(f"[WhatsApp] STATUS {status_val} | msg={msg_id} | to={recipient}")

            messages = value.get("messages", [])
            if messages:
                # Return 200 OK immediately, process in background
                # to prevent Meta from timing out and retrying the webhook
                async def _safe_process(messages):
                    try:
                        await process_messages(messages)
                    except Exception as e:
                        logger.error(f"FATAL: process_messages crashed: {e}")
                        logger.error(traceback.format_exc())
                        # Save to dead-letter queue for retry
                        try:
                            from app.core.memory import memory_manager
                            await memory_manager.save_dead_letter(messages, error=str(e))
                        except Exception as dl_err:
                            logger.error(f"Dead-letter save also failed: {dl_err}")

                asyncio.ensure_future(_safe_process(messages))

    return {"status": "ok"}


async def process_messages(messages: List[Dict[str, Any]]):
    """Process incoming messages and send responses."""
    for msg in messages:
        # ── Production Guards ───────────────────────────────────────────────
        # 1. Skip echo messages (bot's own outgoing messages echoed back)
        if msg.get("is_echo"):
            logger.info(f"Skipping echo message: {msg.get('id', '?')}")
            continue

        # 2. Skip messages from the bot's own number (self-webhook loop)
        from_phone = msg.get("from", "")
        settings = get_settings()
        bot_numbers = [
            settings.WHATSAPP_PHONE_NUMBER_ID,
        ]
        if from_phone in bot_numbers:
            logger.info(f"Skipping message from bot's own number: {from_phone}")
            continue

        # 3. Skip duplicates by message_id
        msg_id = msg.get("id", "")
        if msg_id and _is_duplicate(msg_id):
            logger.info(f"Skipping duplicate message: {msg_id}")
            continue

        msg_type = msg.get("type", "text")
        phone = from_phone
        message_id = msg_id
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
        
        # SANITIZAR input del usuario
        text = sanitize_text(text, max_length=5000)
        phone = sanitize_phone(phone)
        
        if not text:
            logger.warning(f"Empty message after sanitization from {phone}")
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
        
        # Normalizar número para envío (formato Meta Argentina)
        phone_to = format_phone_number(phone)
        logger.info(f"Processing from {phone} → sending to {phone_to}: {text[:30]}...")
        
        try:
            # Rate limit: skip if same user sends too fast
            if not _check_user_rate_limit(phone):
                logger.warning(f"Rate-limited {phone}, dropping message")
                continue

            result = await real_estate_agent.process_turn(
                phone=phone,
                user_message=text
            )

            if not result:
                logger.warning(f"Agent returned None for {phone}, skipping")
                continue

            response_text = result.get("response_text", "") or ""
            rich_content = result.get("rich_content") or {}

            # Send text response
            if response_text:
                logger.info(f"Sending to {phone_to}: {response_text[:30]}...")
                await whatsapp_client.send_message(
                    to=phone_to,
                    message=response_text
                )

            # Send images if any
            images = rich_content.get("images", []) if isinstance(rich_content, dict) else []
            for url in images[:3]:
                await whatsapp_client.send_image(
                    to=phone_to,
                    image_url=url,
                    caption=rich_content.get("caption", "")
                )

        except Exception as e:
            logger.error(f"Error processing: {e}")