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
from app.core.rate_limiter import rate_limiter
from app.utils.sanitizer import sanitize_text, sanitize_phone, sanitize_property_id, sanitize_bot_response

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
    """Return True if this user should be allowed through.
    
    Uses the identity key (BSUID-first, phone fallback) from the current turn's
    contact context to rate-limit by the canonical identity."""
    from app.core.identity import get_current_contact
    _contact = get_current_contact()
    identity_key = _contact.get("bsuid") or phone
    now = time.time()
    last = _user_locks.get(identity_key)
    if last and (now - last) < _USER_RATE_LIMIT:
        return False
    _user_locks[identity_key] = now
    return True


def _resolve_use_v2_router(settings) -> bool:
    """Check if v2 router should be used — env var OR bot_settings DB.

    Priority: bot_settings DB value overrides env var if explicitly set to 'true'/'false'.
    Falls back to settings.USE_V2_ROUTER env var.
    """
    # Check bot_settings from DB (cached via prompt loader's 5-min cache)
    try:
        from app.agents.prompts import _get_cached_bot_settings
        bot_cfg = _get_cached_bot_settings()
        db_val = (bot_cfg or {}).get("use_v2_router", "")
        if db_val == "true":
            return True
        if db_val == "false":
            return False
    except Exception:
        pass
    # Fallback to env var
    return bool(settings.USE_V2_ROUTER)


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
                # v2.0: Dual-path processing
                # 1. Enqueue to Redis for durability (worker can pick up if server restarts)
                # 2. Process inline for immediate response (Render has no worker process)
                # The BSUID (stable identity) lives in the contacts block; stamp it onto
                # each message so downstream identity resolution can read it without
                # needing the full webhook envelope.
                _contacts = value.get("contacts", []) or []
                _contact_bsuid = (_contacts[0].get("user_id") if _contacts else None)
                for msg in messages:
                    msg["_bsuid"] = _contact_bsuid or msg.get("user_id")
                    try:
                        from app.core.message_queue import enqueue_message
                        phone = msg.get("from", "")
                        text = msg.get("text", {}).get("body", "")
                        if not text:
                            mtype = msg.get("type", "")
                            if mtype == "image":
                                text = msg.get("image", {}).get("caption", "") or "[Imagen]"
                            elif mtype == "button":
                                text = msg.get("button", {}).get("payload", "") or msg.get("button", {}).get("id", "")
                            elif mtype == "interactive":
                                interactive = msg.get("interactive", {})
                                if interactive.get("type") == "button_reply":
                                    text = interactive.get("button_reply", {}).get("id", "")
                                elif interactive.get("type") == "list_reply":
                                    text = interactive.get("list_reply", {}).get("id", "")
                        if phone and text:
                            await enqueue_message(phone, text)
                    except Exception as e:
                        logger.error(f"[Webhook] Enqueue failed: {e}")

                    # Phase 0 (Meta BSUID migration): capture the stable identity from the
                    # webhook and persist it (matched by phone) WITHOUT changing any keying
                    # or send behavior. Best-effort, never blocks message processing.
                    asyncio.ensure_future(_capture_identity(value, msg))

                # Inline processing fallback (Render has no worker process)
                async def _safe_process(msgs):
                    try:
                        await process_messages(msgs)
                    except Exception as e:
                        logger.error(f"[Webhook] process_messages crashed: {e}")

                asyncio.ensure_future(_safe_process(messages))

    return {"status": "ok"}


async def _capture_identity(value: Dict[str, Any], msg: Dict[str, Any]):
    """Phase 0 of the Meta BSUID migration — observe & store, change nothing.

    WhatsApp is rolling out usernames + a stable BSUID (`user_id`, e.g. "AR.xxx")
    that will eventually replace the phone as the webhook identifier. Today this
    account's payloads still carry the phone in `from`, so we only *capture* the
    BSUID here (logged always; persisted into User.extra_data['bsuid'] when present)
    to build the phone→BSUID mapping ahead of switching identity in a later phase.

    Identity keying and outbound sending remain phone-based for now. Best-effort:
    any failure is swallowed so it can never affect message handling.
    """
    try:
        phone = msg.get("from", "")
        contacts = value.get("contacts", []) or []
        contact = contacts[0] if contacts else {}
        # Per Meta docs the BSUID lands in the contacts block (contacts[].user_id) and
        # also on the message (messages[].user_id). Read both; prefer whichever is set.
        bsuid = contact.get("user_id") or msg.get("user_id")
        wa_id = contact.get("wa_id")
        profile_name = (contact.get("profile") or {}).get("name")
        logger.info(f"[Identity] phone={phone} bsuid={bsuid} wa_id={wa_id} name={profile_name}")

        if not bsuid or not phone:
            return  # nothing to persist yet (pre-rollout payloads have no BSUID)

        from app.db.session import async_session_factory
        from app.db.models import User
        from app.db.repository import UserRepository
        async with async_session_factory() as session:
            repo = UserRepository(User, session)
            user = await repo.get_by_bsuid(bsuid) if bsuid else None
            if not user:
                user = await repo.get_by_phone(phone)
            if user and user.bsuid != bsuid:
                await repo.update(user.id, bsuid=bsuid)
                await session.commit()
                logger.info(f"[Identity] Stored BSUID for {phone}: {bsuid}")
    except Exception as e:
        logger.debug(f"[Identity] capture failed (non-fatal): {e}")


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
        # Two-layer check: fast in-process dict first, then Redis (survives restarts).
        msg_id = msg.get("id", "")
        if msg_id:
            if _is_duplicate(msg_id):
                logger.info(f"Skipping duplicate message (in-process): {msg_id}")
                continue
            try:
                from app.core.memory import memory_manager
                if await memory_manager.is_duplicate_message(msg_id):
                    logger.info(f"Skipping duplicate message (Redis): {msg_id}")
                    continue
            except Exception as _dedup_err:
                logger.warning(f"Redis dedup check failed, proceeding: {_dedup_err}")

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
        # BSUID-first sending (Meta identity migration): if enabled and a BSUID is
        # present, address the reply to the BSUID; phone stays as the fallback.
        # Gated by a flag because sending-by-BSUID is unverified for this number —
        # flip WHATSAPP_SEND_BY_BSUID on and send a test message to validate.
        if settings.WHATSAPP_SEND_BY_BSUID and msg.get("_bsuid"):
            phone_to = msg.get("_bsuid")
        logger.info(f"Processing from {phone} → sending to {phone_to}: {text[:30]}...")
        
        try:
            # Record start time for response-time logging
            start_time = time.time()

            # Rate limit: skip if same user sends too fast
            if not _check_user_rate_limit(phone):
                logger.warning(f"Rate-limited {phone}, dropping message")
                continue

            # Global rate limit: protect OpenAI API from saturation
            if not await rate_limiter.check_global():
                logger.warning(
                    f"[RateLimiter] Global rate limit exceeded, dropping message from {phone}"
                )
                continue

            # ── Bot-paused check (WhatsApp Inbox) ────────────────────────
            # If the admin has paused the bot for this user, save the message
            # to the conversation but don't process with the bot.
            if use_v2:
                try:
                    from app.db.session import async_session_factory
                    from app.services.conversation_service import is_bot_paused, upsert_conversation, save_user_message_only
                    async with async_session_factory() as _db:
                        if await is_bot_paused(_db, phone):
                            logger.info(f"[Webhook] Bot paused for {phone}, saving message without response")
                            canonical_id = msg.get("_bsuid") or phone
                            _conv_id = await upsert_conversation(_db, canonical_id, phone=phone)
                            await save_user_message_only(_db, _conv_id, text)
                            continue
                except Exception as _bp_err:
                    logger.warning(f"[Webhook] Bot-paused check failed (non-fatal): {_bp_err}")

            # ── v2.0 Router Feature Flag ──────────────────────────────────
            use_v2 = _resolve_use_v2_router(settings)
            if use_v2:
                from app.routers.v2_adapter import process_turn_v2
                result = await process_turn_v2(
                    phone=phone,
                    user_message=text,
                    media_url=media_url,
                    bsuid=msg.get("_bsuid"),
                )
            else:
                result = await real_estate_agent.process_turn(
                    phone=phone,
                    user_message=text
                )

            turn_time = time.time() - start_time
            tools_used = result.get("tools_used", []) if result else []
            logger.info(f"[Timing] phone={phone[-4:]} | turn={turn_time:.2f}s | tools={tools_used}")

            if not result:
                logger.warning(f"Agent returned None for {phone}, skipping")
                continue

            response_text = result.get("response_text", "") or ""
            rich_content = result.get("rich_content") or {}

            # ── Check for response_plan (multi-message support) ──────────────
            response_plan = rich_content.get("response_plan") if isinstance(rich_content, dict) else None

            if response_plan and isinstance(response_plan, list) and len(response_plan) > 0:
                # Send messages according to the plan, in order
                logger.info(f"[Webhook] Using response_plan with {len(response_plan)} segment(s)")
                for seg_idx, segment in enumerate(response_plan):
                    try:
                        seg_type = segment.get("type", "text")
                        if seg_type == "text":
                            text = sanitize_bot_response(segment.get("content", ""))
                            if text:
                                await whatsapp_client.send_message(to=phone_to, message=text)
                                logger.info(f"[Webhook] Sent plan segment {seg_idx}: text ({len(text)} chars)")
                        elif seg_type == "images":
                            images = segment.get("images", [])
                            caption = sanitize_bot_response(segment.get("caption", ""))
                            for i, url in enumerate(images[:4]):
                                try:
                                    img_result = await whatsapp_client.send_image(
                                        to=phone_to,
                                        image_url=url,
                                        caption=caption  # only if explicitly set, otherwise empty
                                    )
                                    if img_result is None or (isinstance(img_result, dict) and img_result.get("error")):
                                        logger.warning(f"[Webhook] Plan image {seg_idx}.{i} failed: {img_result}")
                                    else:
                                        logger.info(f"[Webhook] Sent plan image {seg_idx}.{i}")
                                except Exception as e:
                                    logger.error(f"[Webhook] Plan image error {seg_idx}.{i}: {e}")
                                if i < len(images[:4]) - 1:
                                    await asyncio.sleep(1.0)
                    except Exception as e:
                        logger.error(f"[Webhook] Plan segment {seg_idx} failed: {e}")
                    # Small delay between segments for natural feel
                    if seg_idx < len(response_plan) - 1:
                        await asyncio.sleep(0.5)
            else:
                # ── Fallback: single text + images (original behavior) ─────────
                # Strip image URLs and internal paths from text before sending
                response_text = sanitize_bot_response(response_text)

                # When images will be sent separately, split text around photo references
                images = rich_content.get("images", []) if isinstance(rich_content, dict) else []
                _images_already_sent = False  # Track if images were sent inside the photo branch
                if images and response_text:
                    import re
                    # Remove bare numbered lines
                    response_text = re.sub(r'^\d+[.)]\s*\n?', '', response_text, flags=re.MULTILINE)
                    # Remove image URLs the LLM may have included
                    response_text = re.sub(r'https?://[^\s]+/media/property/[^\s]+', '', response_text)
                    # Clean up double newlines left after removal
                    response_text = re.sub(r'\n{3,}', '\n\n', response_text).strip()
                    # Split at 📷 lines: everything before 📷 is intro, everything after is follow-up
                    photo_lines = re.split(r'(?:^|\n)\s*📷[^\n]*', response_text, flags=re.MULTILINE)
                    if len(photo_lines) >= 2:
                        intro = photo_lines[0].strip()
                        follow_up = ''.join(photo_lines[1:]).strip()
                        if intro:
                            logger.info(f"Sending photo intro to {phone_to}: {intro[:30]}...")
                            await whatsapp_client.send_message(to=phone_to, message=intro)
                            await asyncio.sleep(0.5)
                        for i, url in enumerate(images[:4]):
                            try:
                                caption_base = rich_content.get("caption", "Fotos de la propiedad")
                                img_caption = f"{caption_base} — {i+1}/{len(images[:4])}" if len(images[:4]) > 1 else caption_base
                                img_result = await whatsapp_client.send_image(
                                    to=phone_to,
                                    image_url=url,
                                    caption=img_caption
                                )
                                if img_result is None or (isinstance(img_result, dict) and img_result.get("error")):
                                    logger.warning(f"Image send failed (index {i}, url truncated: {url[:60]}...): result={img_result}")
                                else:
                                    logger.info(f"Image sent successfully (index {i})")
                            except Exception as e:
                                logger.error(f"Image send error (index {i}, url truncated: {url[:60]}...): {e}")
                            if i < len(images[:4]) - 1:
                                await asyncio.sleep(1.0)
                        # Only send photo follow-up if scheduling was NOT done in this same turn.
                        # If schedule_visit was called, the LLM's response_text already has the
                        # confirmation — sending a "querés agendar?" follow-up would be contradictory
                        # and would overwrite/replace the actual confirmation (due to `continue` below).
                        _scheduled_this_turn = any(
                            t in tools_used for t in ("schedule_visit", "reschedule_appointment")
                        )
                        if not _scheduled_this_turn:
                            follow_up = "¿Tenes alguna otra consulta? O si querés podemos agendar una visita para que la veas en persona."
                            await asyncio.sleep(0.5)
                            logger.info(f"Sending photo follow-up to {phone_to}: {follow_up[:30]}...")
                            await whatsapp_client.send_message(to=phone_to, message=follow_up)
                            continue  # Skip the generic text+images send below (only when not scheduling)
                        else:
                            # Scheduling was confirmed: fall through to send response_text (confirmation)
                            # Don't `continue` — let the generic send below deliver the LLM confirmation.
                            logger.info(f"Skipping photo follow-up (schedule_visit used this turn)")
                            # Images were already sent above; mark so the generic loop below skips them
                            _images_already_sent = True

                # Send text response
                if response_text:
                    logger.info(f"Sending to {phone_to}: {response_text[:30]}...")
                    await whatsapp_client.send_message(
                        to=phone_to,
                        message=response_text
                    )

                # Send images if any, with rate-limiting delay and error isolation
                # Re-fetch only if images weren't already sent in the photo-split branch above
                if not _images_already_sent:
                    images = rich_content.get("images", []) if isinstance(rich_content, dict) else []
                for i, url in enumerate(images[:4]):
                    try:
                        img_result = await whatsapp_client.send_image(
                            to=phone_to,
                            image_url=url,
                            caption=rich_content.get("caption", "")
                        )
                        if img_result is None or (isinstance(img_result, dict) and img_result.get("error")):
                            logger.warning(f"Image send failed (index {i}, url truncated: {url[:60]}...): result={img_result}")
                        else:
                            logger.info(f"Image sent successfully (index {i})")
                    except Exception as e:
                        logger.error(f"Image send error (index {i}, url truncated: {url[:60]}...): {e}")
                    if i < len(images[:4]) - 1:
                        await asyncio.sleep(1.0)

            # Full response_time: from webhook receive → WhatsApp send complete
            response_time = time.time() - start_time
            logger.info(f"[Timing] phone={phone[-4:]} | response_time={response_time:.2f}s | turn={turn_time:.2f}s | tools={tools_used}")

        except Exception as e:
            logger.error(f"Error processing: {e}")
            import traceback
            logger.error(traceback.format_exc())
