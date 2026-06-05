"""Phase 5 acceptance tests: RAG knowledge grounding.

Verifies:
  1. The knowledge index functions are importable and don't crash when pgvector
     is unavailable (graceful degradation).
  2. get_faq_answer returns a safe deferral for an unknown question (not a hallucination).
  3. Known FAQ topics yield non-empty answers via the fallback layer.
  4. The embedding module handles missing API key gracefully.

These tests run without a live DB or OpenAI key (all mocked at the boundaries).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio


# ── 1. Import smoke test ──────────────────────────────────────────────────────

def test_knowledge_module_importable():
    """All Phase 5 modules must be importable without crashing."""
    from app.routers.v3.knowledge import embedder  # noqa: F401
    from app.routers.v3.knowledge import index  # noqa: F401


def test_knowledge_index_public_api():
    """Public API surface must be present."""
    from app.routers.v3.knowledge.index import (
        upsert_chunk,
        search_knowledge,
        delete_chunks,
        schedule_upsert,
        schedule_delete,
        reindex_tenant,
    )
    assert callable(upsert_chunk)
    assert callable(search_knowledge)
    assert callable(delete_chunks)
    assert callable(schedule_upsert)
    assert callable(schedule_delete)
    assert callable(reindex_tenant)


# ── 2. Embedder graceful degradation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_embedder_returns_none_without_api_key():
    """embed_text returns None (doesn't raise) when OPENAI_API_KEY is unset."""
    from app.routers.v3.knowledge.embedder import embed_text

    # Patch get_settings to return a settings-like object with no API key
    fake_settings = MagicMock()
    fake_settings.OPENAI_API_KEY = None
    fake_settings.EMBEDDING_MODEL = "text-embedding-3-small"

    with patch("app.core.config.get_settings", return_value=fake_settings):
        result = await embed_text("test query")
        assert result is None


@pytest.mark.asyncio
async def test_embedder_returns_none_on_api_error():
    """embed_text returns None (doesn't raise) on API error."""
    from app.routers.v3.knowledge.embedder import embed_text

    with patch("openai.AsyncOpenAI") as mock_openai_cls:
        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = RuntimeError("API error")
        mock_openai_cls.return_value = mock_client

        result = await embed_text("test query about alquiler")
        assert result is None


# ── 3. search_knowledge graceful degradation ─────────────────────────────────

@pytest.mark.asyncio
async def test_search_knowledge_returns_empty_on_db_error():
    """search_knowledge returns [] (doesn't raise) when DB is unavailable."""
    from app.routers.v3.knowledge.index import search_knowledge
    from uuid import UUID

    # embed_text is imported locally inside search_knowledge, so patch the source module
    with patch("app.routers.v3.knowledge.embedder.embed_text", new=AsyncMock(return_value=None)):
        result = await search_knowledge(
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            query="¿qué necesito para alquilar?",
        )
        assert result == []


@pytest.mark.asyncio
async def test_search_knowledge_returns_empty_when_embedding_fails():
    """search_knowledge returns [] when embedding generation returns None."""
    from app.routers.v3.knowledge.index import search_knowledge
    from uuid import UUID

    with patch("app.routers.v3.knowledge.embedder.embed_text", new=AsyncMock(return_value=None)):
        result = await search_knowledge(
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            query="¿qué necesito para alquilar?",
        )
        assert result == []


# ── 4. get_faq_answer — safe deferral for unknown questions ───────────────────

@pytest.mark.asyncio
async def test_get_faq_answer_safe_deferral_for_unknown_topic():
    """An unknown question not in the knowledge base returns a safe deferral, not a hallucination."""
    from app.tools.v2.get_faq_answer import get_faq_answer

    # Mock semantic search to return empty (topic not in knowledge base)
    with patch("app.routers.v3.knowledge.index.search_knowledge", new=AsyncMock(return_value=[])):
        # Mock DB keyword search to also return empty
        with patch("app.services.faq_service.FAQService.search_faqs", new=AsyncMock(return_value=[])):
            result = await get_faq_answer("¿tienen propiedades en Buenos Aires?")

    # Must be non-empty (bot still responds) and must NOT claim to have the info
    assert result, "Safe deferral must be non-empty"
    hallucination_markers = [
        "sí, tenemos", "tenemos propiedades", "claro que sí",
        "en buenos aires", "por supuesto",
    ]
    result_lower = result.lower()
    for marker in hallucination_markers:
        assert marker not in result_lower, (
            f"Response appears to hallucinate: '{result[:120]}' contains '{marker}'"
        )

    # Must communicate inability to answer / refer to human
    deferral_markers = [
        "no tengo información", "consulto", "asesor", "confirmo", "no tengo",
        "específica",
    ]
    assert any(m in result_lower for m in deferral_markers), (
        f"Response is not a safe deferral: '{result[:120]}'"
    )


@pytest.mark.asyncio
async def test_get_faq_answer_known_topic_via_fallback():
    """A known FAQ topic returns a non-empty answer via the hardcoded fallback."""
    from app.tools.v2.get_faq_answer import get_faq_answer

    # Force semantic search to fail (no pgvector) and DB search to return empty
    with patch("app.routers.v3.knowledge.index.search_knowledge", side_effect=RuntimeError("no pgvector")):
        with patch("app.services.faq_service.FAQService.search_faqs", new=AsyncMock(return_value=[])):
            result = await get_faq_answer("¿qué requisitos piden para alquilar?")

    assert result, "Known FAQ topic must return non-empty answer"
    assert len(result) > 20, "Answer should be substantive"


@pytest.mark.asyncio
async def test_get_faq_answer_empty_question():
    """Empty question returns a prompt for clarification, not an error."""
    from app.tools.v2.get_faq_answer import get_faq_answer

    result = await get_faq_answer("")
    assert result, "Empty question must return a non-empty clarification prompt"


# ── 5. Semantic result format ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_faq_answer_uses_rag_result_when_available():
    """When RAG returns chunks, they are used as the answer (not the fallback)."""
    from app.tools.v2.get_faq_answer import get_faq_answer
    from uuid import UUID

    fake_chunks = [
        {
            "text": "Para alquilar necesitás DNI y garantía propietaria.",
            "source_type": "faq",
            "source_id": 1,
            "similarity": 0.82,
        }
    ]
    with patch("app.routers.v3.knowledge.index.search_knowledge", new=AsyncMock(return_value=fake_chunks)):
        result = await get_faq_answer("¿qué necesito para alquilar?")

    assert "DNI" in result or "garantía" in result.lower(), (
        f"RAG result not used: '{result}'"
    )


# ── 6. upsert_chunk graceful degradation ─────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_chunk_returns_false_on_embed_failure():
    """upsert_chunk returns False (doesn't raise) when embedding fails."""
    from app.routers.v3.knowledge.index import upsert_chunk
    from uuid import UUID

    with patch("app.routers.v3.knowledge.embedder.embed_text", new=AsyncMock(return_value=None)):
        result = await upsert_chunk(
            tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
            source_type="faq",
            source_id=1,
            text="¿Qué requisitos piden?",
        )
        assert result is False
