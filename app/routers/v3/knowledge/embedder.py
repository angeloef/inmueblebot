"""OpenAI text-embedding-3-small wrapper (Phase 5 RAG).

Dimensions: 1536 (text-embedding-3-small default).
Cost: ~$0.02 / 1M tokens — negligible at this scale.
Never raises — errors return None so callers can skip embedding gracefully.
"""
from __future__ import annotations

from typing import Optional
from loguru import logger


async def embed_text(text: str) -> Optional[list[float]]:
    """Generate a 1536-dim embedding for *text*. Returns None on failure."""
    if not text or not text.strip():
        return None
    try:
        from openai import AsyncOpenAI
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            logger.debug("[RAG] No OPENAI_API_KEY — skipping embedding")
            return None

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text[:8000],  # guard against token limit
        )
        return resp.data[0].embedding
    except Exception as exc:
        logger.debug("[RAG] embed_text failed: {}", str(exc))
        return None


async def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """Batch-embed multiple texts concurrently. Returns a list parallel to *texts*."""
    import asyncio

    tasks = [embed_text(t) for t in texts]
    return list(await asyncio.gather(*tasks))
