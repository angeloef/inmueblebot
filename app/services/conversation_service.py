"""
WhatsApp Inbox — Conversation Service.

Handles conversation persistence, message CRUD, and SSE real-time streaming
for the admin dashboard inbox feature.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import resolve_tenant_id
from app.db.models import Conversation, Message, User
from app.db.repository import ConversationRepository, MessageRepository

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Schema self-healing — ensures required columns exist before first use.
# The admin.py startup migration only fires on sync admin endpoint calls;
# the async webhook path reaches this module first.
# ═══════════════════════════════════════════════════════════════════════

_schema_ensured = False


async def _ensure_schema(session: AsyncSession) -> None:
    """Verify schema readiness. Actual migrations run in admin.py startup.
    If columns are missing, admin.py's _run_startup_migration hasn't fired
    yet — the caller should gracefully degrade until an admin endpoint
    triggers the migration."""
    global _schema_ensured
    if _schema_ensured:
        return
    _schema_ensured = True  # only log once
    try:
        from sqlalchemy import text as _text
        result = await session.execute(_text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'id'"
        ))
        if not result.scalar():
            logger.warning(
                "messages table not ready — hit any /admin endpoint to "
                "trigger startup migration, then retry"
            )
    except Exception as e:
        logger.warning("Schema readiness check skipped: %s", e)

# ═══════════════════════════════════════════════════════════════════════
# SSE Pub/Sub — in-memory
# ═══════════════════════════════════════════════════════════════════════

_subscribers: dict[str, list[asyncio.Queue]] = {}


def subscribe(conversation_id: str) -> asyncio.Queue:
    """Return a new queue subscribed to events for this conversation."""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(conversation_id, []).append(q)
    return q


def unsubscribe(conversation_id: str, q: asyncio.Queue) -> None:
    """Remove a queue from the subscriber list for this conversation."""
    subs = _subscribers.get(conversation_id, [])
    if q in subs:
        subs.remove(q)
    if not subs:
        _subscribers.pop(conversation_id, None)


async def publish(conversation_id: str, event: dict) -> None:
    """Push an event dict to all subscriber queues for this conversation."""
    subs = _subscribers.get(conversation_id, [])
    if not subs:
        return
    payload = json.dumps(event, default=str)
    for q in subs:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for conversation %s, dropping event", conversation_id)


# ═══════════════════════════════════════════════════════════════════════
# Core Service Functions
# ═══════════════════════════════════════════════════════════════════════


async def upsert_conversation(
    session: AsyncSession,
    session_id: str,
    phone: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> UUID:
    """Find existing Conversation by session_id within matching user, or create new.

    User lookup priority: user_id → phone (User.whatsapp_phone) → create new user.
    Returns conversation.id (UUID).
    """
    await _ensure_schema(session)
    from app.db.repository import UserRepository
    repo = UserRepository(User, session)
    user = None

    if user_id:
        user = await repo.get(user_id)
    if not user and phone:
        user = await repo.get_or_create(phone=phone)
    if not user:
        user = await repo.get_or_create(phone=phone or f"anon-{session_id}")

    # Find existing conversation by session_id within this user
    conv_repo = ConversationRepository(Conversation, session)
    existing = await conv_repo.get_by_session(session_id)

    if existing and existing.user_id == user.id:
        return existing.id

    # Create new conversation. tenant_id REQUIRED: RLS WITH CHECK rejects NULL and a
    # NULL-tenant conversation would be invisible to the dashboard's tenant-scoped queries.
    conv = Conversation(
        id=uuid4(),
        tenant_id=resolve_tenant_id(),
        user_id=user.id,
        session_id=session_id,
        state="idle",
    )
    session.add(conv)
    await session.flush()
    await session.refresh(conv)
    await session.commit()
    logger.info("Created conversation %s for user %s session %s", conv.id, user.id, session_id)
    return conv.id


async def save_turn(
    session: AsyncSession,
    conversation_id: UUID,
    user_message: str,
    bot_response: str,
    tools_called: Optional[list[str]] = None,
    router: Optional[str] = None,
    latency_ms: float = 0,
    confidence: float = 0,
) -> None:
    """Insert user message + bot response, update conversation.last_message_at."""
    from sqlalchemy import text as _text
    now = datetime.now(timezone.utc)

    # Generate UUIDs — the Render DB's messages.id is UUID, not Integer
    uid1, uid2 = str(uuid4()), str(uuid4())

    # Insert user message (CAST avoids text() bind-param collision with ::uuid)
    await session.execute(_text(
        "INSERT INTO messages (id, conversation_id, role, sender, content, "
        "timestamp) VALUES (CAST(:id AS uuid), CAST(:cid AS uuid), "
        ":role, :sender, :content, :ts)"
    ), {"id": uid1, "cid": str(conversation_id), "role": "user",
        "sender": "user", "content": user_message, "ts": now})
    user_msg_id = uid1

    # SSE notification for user message
    await publish(str(conversation_id), {
        "type": "new_message",
        "message": {
            "id": uid1,
            "role": "user",
            "sender": "user",
            "content": user_message,
            "timestamp": now.isoformat(),
            "metadata": None,
        },
    })

    # Insert bot message
    metadata_json = json.dumps({
        "tools_called": tools_called or [],
        "router": router or "",
        "latency_ms": latency_ms,
        "confidence": confidence,
    })
    await session.execute(_text(
        "INSERT INTO messages (id, conversation_id, role, sender, content, "
        "msg_metadata, timestamp) VALUES "
        "(CAST(:id AS uuid), CAST(:cid AS uuid), :role, :sender, "
        ":content, CAST(:meta AS jsonb), :ts)"
    ), {"id": uid2, "cid": str(conversation_id), "role": "assistant",
        "sender": "bot", "content": bot_response, "meta": metadata_json,
        "ts": now})

    # Update conversation timestamp
    stmt = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=now)
    )
    await session.execute(stmt)
    await session.commit()

    # SSE notification
    await publish(str(conversation_id), {
        "type": "new_message",
        "message": {
            "id": uid2,
            "role": "assistant",
            "sender": "bot",
            "content": bot_response,
            "timestamp": now.isoformat(),
            "metadata": json.loads(metadata_json),
        },
    })


async def save_user_message_only(
    session: AsyncSession,
    conversation_id: UUID,
    text: str,
) -> None:
    """Insert only a user message (no bot response). Used when bot is paused."""
    from sqlalchemy import text as _text
    now = datetime.now(timezone.utc)

    uid = str(uuid4())

    await session.execute(_text(
        "INSERT INTO messages (id, conversation_id, role, sender, content, "
        "timestamp) VALUES (CAST(:id AS uuid), CAST(:cid AS uuid), "
        ":role, :sender, :content, :ts)"
    ), {"id": uid, "cid": str(conversation_id), "role": "user",
        "sender": "user", "content": text, "ts": now})

    stmt = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_message_at=now)
    )
    await session.execute(stmt)
    await session.commit()

    await publish(str(conversation_id), {
        "type": "new_message",
        "message": {
            "id": uid,
            "role": "user",
            "sender": "user",
            "content": text,
            "timestamp": now.isoformat(),
            "metadata": None,
        },
    })


async def save_admin_message(
    session: AsyncSession,
    conversation_id: UUID,
    text: str,
) -> dict:
    """Insert admin reply message and optionally set bot_paused=True.

    Returns dict with id, timestamp, sender.
    """
    now = datetime.now(timezone.utc)
    # tenant_id must equal the session GUC for RLS WITH CHECK to pass (NULL is rejected).
    # resolve_tenant_id() returns exactly what the GUC listener set. See create_property.
    msg = Message(
        tenant_id=resolve_tenant_id(),
        conversation_id=conversation_id,
        role="assistant",
        sender="admin",
        content=text,
        timestamp=now,
    )
    session.add(msg)

    # Auto-pause bot when admin replies
    conv = await session.get(Conversation, conversation_id)
    if conv:
        if not conv.bot_paused:
            conv.bot_paused = True
        conv.last_message_at = now
    else:
        logger.warning("Conversation %s not found for save_admin_message", conversation_id)
    await session.commit()

    result = {
        "id": str(msg.id),
        "timestamp": now.isoformat(),
        "sender": "admin",
    }

    # SSE notification
    await publish(str(conversation_id), {
        "type": "new_message",
        "message": {
            "id": msg.id,
            "role": "assistant",
            "sender": "admin",
            "content": text,
            "timestamp": now.isoformat(),
            "metadata": None,
        },
    })
    await publish(str(conversation_id), {
        "type": "bot_paused",
        "bot_paused": True,
    })

    return result


async def list_conversations(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return conversations with user info, sorted by last_message_at DESC.

    Each item: id, phone, bsuid, last_message_at, state, turn_count, bot_paused,
    last_sender.
    """
    await _ensure_schema(session)
    # Subquery: count messages per conversation
    msg_count = (
        select(
            Message.conversation_id,
            func.count(Message.id).label("turn_count"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    # Correlated subquery: sender of the most recent message per conversation.
    # Lets the dashboard tell apart a paused chat awaiting a human reply
    # (last_sender == 'user') from one a human is already handling.
    last_sender = (
        select(Message.sender)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.timestamp.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
        .label("last_sender")
    )

    query = (
        select(
            Conversation,
            User.whatsapp_phone,
            User.bsuid,
            func.coalesce(msg_count.c.turn_count, 0).label("turn_count"),
            last_sender,
        )
        .join(User, Conversation.user_id == User.id)
        .outerjoin(msg_count, msg_count.c.conversation_id == Conversation.id)
        .order_by(desc(func.coalesce(Conversation.last_message_at, Conversation.created_at)))
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(query)
    rows = result.all()

    conversations = []
    for conv, phone, bsuid, turn_count, last_sender_value in rows:
        conversations.append({
            "id": str(conv.id),
            "phone": phone,
            "bsuid": bsuid,
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "state": conv.state,
            "turn_count": turn_count,
            "bot_paused": conv.bot_paused,
            "last_sender": last_sender_value,
        })
    return conversations


async def get_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> Optional[dict]:
    """Return conversation with all messages ordered by timestamp."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        return None

    # Load user
    user = await session.get(User, conv.user_id)
    phone = user.whatsapp_phone if user else None
    bsuid = user.bsuid if user else None

    # Load messages
    msgs_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
    )
    messages = msgs_result.scalars().all()

    return {
        "id": str(conv.id),
        "phone": phone,
        "bsuid": bsuid,
        "state": conv.state,
        "bot_paused": conv.bot_paused,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "sender": m.sender,
                "content": m.content,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "metadata": m.msg_metadata,
            }
            for m in messages
        ],
    }


async def toggle_bot(
    session: AsyncSession,
    conversation_id: UUID,
) -> dict:
    """Flip bot_paused boolean and return new value."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        raise ValueError("Conversation not found")

    conv.bot_paused = not conv.bot_paused
    await session.commit()

    new_value = conv.bot_paused

    # SSE notification
    await publish(str(conversation_id), {
        "type": "bot_paused",
        "bot_paused": new_value,
    })

    return {"bot_paused": new_value}


async def get_user_phone_for_conversation(
    session: AsyncSession,
    conversation_id: UUID,
) -> Optional[str]:
    """Return user's bsuid first, fallback whatsapp_phone."""
    conv = await session.get(Conversation, conversation_id)
    if not conv:
        return None
    user = await session.get(User, conv.user_id)
    if not user:
        return None
    return user.whatsapp_phone or user.bsuid


async def is_bot_paused(
    session: AsyncSession,
    phone: str,
) -> bool:
    """Check if any active conversation for this user has bot_paused=True."""
    await _ensure_schema(session)
    # Find user by phone
    user_result = await session.execute(
        select(User).where(User.whatsapp_phone == phone)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        return False

    # Check if any active conversation has bot_paused=True
    conv_result = await session.execute(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.bot_paused == True,  # noqa: E712
        )
        .limit(1)
    )
    conv = conv_result.scalar_one_or_none()
    return conv is not None
