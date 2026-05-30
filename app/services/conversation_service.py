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

from app.db.models import Conversation, Message, User
from app.db.repository import ConversationRepository, MessageRepository

logger = logging.getLogger(__name__)

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

    # Create new conversation
    conv = Conversation(
        id=uuid4(),
        user_id=user.id,
        session_id=session_id,
        state="idle",
    )
    session.add(conv)
    await session.flush()
    await session.refresh(conv)
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
    now = datetime.now(timezone.utc)

    # Insert user message
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        sender="user",
        content=user_message,
        timestamp=now,
    )
    session.add(user_msg)

    # Insert bot message with metadata
    metadata = {
        "tools_called": tools_called or [],
        "router": router or "",
        "latency_ms": latency_ms,
        "confidence": confidence,
    }
    bot_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        sender="bot",
        content=bot_response,
        msg_metadata=metadata,
        timestamp=now,
    )
    session.add(bot_msg)

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
            "id": bot_msg.id,
            "role": "assistant",
            "sender": "bot",
            "content": bot_response,
            "timestamp": now.isoformat(),
            "metadata": metadata,
        },
    })


async def save_user_message_only(
    session: AsyncSession,
    conversation_id: UUID,
    text: str,
) -> None:
    """Insert only a user message (no bot response). Used when bot is paused."""
    now = datetime.now(timezone.utc)
    msg = Message(
        conversation_id=conversation_id,
        role="user",
        sender="user",
        content=text,
        timestamp=now,
    )
    session.add(msg)

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
            "id": msg.id,
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
    msg = Message(
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

    Each item: id, phone, bsuid, last_message_at, state, turn_count, bot_paused.
    """
    # Subquery: count messages per conversation
    msg_count = (
        select(
            Message.conversation_id,
            func.count(Message.id).label("turn_count"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    query = (
        select(
            Conversation,
            User.whatsapp_phone,
            User.bsuid,
            func.coalesce(msg_count.c.turn_count, 0).label("turn_count"),
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
    for conv, phone, bsuid, turn_count in rows:
        conversations.append({
            "id": str(conv.id),
            "phone": phone,
            "bsuid": bsuid,
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "state": conv.state,
            "turn_count": turn_count,
            "bot_paused": conv.bot_paused,
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
    return user.bsuid or user.whatsapp_phone


async def is_bot_paused(
    session: AsyncSession,
    phone: str,
) -> bool:
    """Check if any active conversation for this user has bot_paused=True."""
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
