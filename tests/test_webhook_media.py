"""Offline unit tests for non-text WhatsApp message handling in process_messages.

Covers the P0/P1 fix: audio, stickers, images, video, documents and any other
non-text message type get a single polite "text only" reply instead of being
silently dropped or fed to the LLM as a "[Audio]"/"[Imagen]" placeholder.

No DB / Redis / LLM — all I/O boundaries are mocked.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.routes import webhook


def _fake_settings():
    """Minimal settings object touched by the unsupported-media path."""
    return SimpleNamespace(
        WHATSAPP_PHONE_NUMBER_ID="000000000",
        WHATSAPP_SEND_BY_BSUID=False,
    )


def _msg(msg_type: str, msg_id: str, **payload):
    base = {"from": "5493750000001", "id": msg_id, "type": msg_type, "timestamp": "0"}
    base.update(payload)
    return base


@pytest.fixture(autouse=True)
def _reset_dedup_and_ratelimit():
    """Each test starts with clean dedup + rate-limit state (module-level dicts)."""
    webhook._processed_ids.clear()
    webhook._user_locks.clear()
    yield
    webhook._processed_ids.clear()
    webhook._user_locks.clear()


@pytest.fixture(autouse=True)
def _no_inbox_writes():
    """Keep media tests offline — stub conversation persistence.

    The media fallback now records a placeholder message in the inbox so the admin
    sees what the user sent. These unit tests verify only the WhatsApp reply behavior,
    not DB writes, so stub the inbox side-effect.
    """
    with patch(
        "app.services.conversation_service.upsert_conversation",
        new_callable=AsyncMock,
        return_value="fake-conv-id",
    ), \
         patch(
        "app.services.conversation_service.save_user_message_only",
        new_callable=AsyncMock,
    ):
        yield


def test_media_placeholder_mapping():
    """Verify media type → emoji placeholder mapping."""
    from app.api.routes.webhook import _media_placeholder

    assert _media_placeholder("audio") == "🎵 Audio message"
    assert _media_placeholder("image") == "📷 Image"
    assert _media_placeholder("video") == "🎬 Video"
    assert _media_placeholder("document") == "📎 Document"
    assert _media_placeholder("sticker") == "🎨 Sticker"
    assert _media_placeholder("location") == "📍 Location"
    assert _media_placeholder("contacts") == "👥 Contact(s)"
    # Unknown type gets fallback
    assert _media_placeholder("unknown") == "📦 Unknown message"


@pytest.mark.parametrize("msg_type", ["audio", "image", "video", "document", "sticker", "reaction", "location"])
async def test_unsupported_type_gets_polite_reply(msg_type):
    send = AsyncMock()
    dedup = AsyncMock(return_value=False)
    with patch.object(webhook, "get_settings", _fake_settings), \
         patch.object(webhook.whatsapp_client, "send_message", send), \
         patch("app.core.memory.memory_manager.is_duplicate_message", dedup):
        await webhook.process_messages([_msg(msg_type, f"wamid.{msg_type}")], phone_number_id=None)

    send.assert_awaited_once()
    kwargs = send.await_args.kwargs
    assert kwargs["message"] == webhook._UNSUPPORTED_MEDIA_REPLY


async def test_audio_is_not_routed_to_llm():
    """Audio must short-circuit before any router/engine dispatch."""
    send = AsyncMock()
    dedup = AsyncMock(return_value=False)
    v3 = AsyncMock()
    with patch.object(webhook, "get_settings", _fake_settings), \
         patch.object(webhook.whatsapp_client, "send_message", send), \
         patch.object(webhook, "_process_turn_v3_or_fallback", v3), \
         patch("app.core.memory.memory_manager.is_duplicate_message", dedup):
        await webhook.process_messages([_msg("audio", "wamid.audio2")], phone_number_id=None)

    v3.assert_not_called()
    send.assert_awaited_once()


async def test_text_message_is_not_intercepted():
    """A real text message must NOT hit the unsupported-media reply."""
    send = AsyncMock()
    dedup = AsyncMock(return_value=False)
    v3 = AsyncMock(return_value={"response_text": "hola!", "tools_used": []})
    with patch.object(webhook, "get_settings", _fake_settings), \
         patch.object(webhook.whatsapp_client, "send_message", send), \
         patch.object(webhook, "_process_turn_v3_or_fallback", v3), \
         patch.object(webhook, "_resolve_active_router", lambda _s: "v3"), \
         patch("app.core.memory.memory_manager.is_duplicate_message", dedup), \
         patch("app.core.rate_limiter.rate_limiter.check_global", AsyncMock(return_value=True)), \
         patch("app.db.session.async_session_factory"), \
         patch("app.services.conversation_service.is_bot_paused", AsyncMock(return_value=False)):
        await webhook.process_messages(
            [_msg("text", "wamid.text1", text={"body": "hola"})], phone_number_id=None
        )

    # The polite media reply must never be sent for a text message.
    sent_messages = [c.kwargs.get("message") for c in send.await_args_list]
    assert webhook._UNSUPPORTED_MEDIA_REPLY not in sent_messages
    v3.assert_awaited_once()
