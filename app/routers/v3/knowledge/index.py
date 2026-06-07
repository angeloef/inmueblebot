"""Knowledge index — pgvector store for FAQ + property description chunks (Phase 5).

Uses raw SQL for all vector operations to avoid asyncpg/pgvector codec registration
complexity. Vectors are passed as Postgres text literal '[f1, f2, ...]::vector'.

Table: knowledge_chunks
  id            BIGSERIAL PRIMARY KEY
  tenant_id     UUID NOT NULL
  source_type   VARCHAR(20) NOT NULL  — 'faq' | 'property'
  source_id     BIGINT NOT NULL
  chunk_text    TEXT NOT NULL
  embedding     VECTOR(1536)
  updated_at    TIMESTAMPTZ DEFAULT NOW()
  UNIQUE (tenant_id, source_type, source_id)

Similarity metric: cosine (operator <=>). A result is "relevant" when
1 - cosine_distance >= SIMILARITY_THRESHOLD (configurable via KNOWLEDGE_SIMILARITY_THRESHOLD).

Graceful degradation: every public function is wrapped in try/except; if the
knowledge_chunks table does not exist yet (migration pending) or pgvector is not
enabled, the function returns an empty list / False and logs a debug message.
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from loguru import logger

# Cosine similarity floor — results below this threshold are ignored.
_DEFAULT_THRESHOLD = 0.50


async def upsert_chunk(
    tenant_id: UUID,
    source_type: str,
    source_id: int,
    text: str,
) -> bool:
    """Embed *text* and upsert into knowledge_chunks.

    Returns True on success, False if embedding or DB write failed.
    Safe to call fire-and-forget.
    """
    try:
        from app.routers.v3.knowledge.embedder import embed_text
        from app.db.session import async_session_factory
        from sqlalchemy import text as sql_text

        embedding = await embed_text(text)
        if embedding is None:
            return False

        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

        async with async_session_factory() as session:
            await session.execute(
                sql_text("""
                    INSERT INTO knowledge_chunks
                        (tenant_id, source_type, source_id, chunk_text, embedding)
                    VALUES
                        (:tid, :stype, :sid, :txt, CAST(:emb AS vector))
                    ON CONFLICT (tenant_id, source_type, source_id)
                    DO UPDATE SET
                        chunk_text = EXCLUDED.chunk_text,
                        embedding  = EXCLUDED.embedding,
                        updated_at = NOW()
                """),
                {
                    "tid": str(tenant_id),
                    "stype": source_type,
                    "sid": source_id,
                    "txt": text[:4000],
                    "emb": vec_literal,
                },
            )
            await session.commit()
        logger.debug("[RAG] upserted chunk tenant={} type={} id={}", tenant_id, source_type, source_id)
        return True
    except Exception as exc:
        logger.debug("[RAG] upsert_chunk failed (tenant={} type={} id={}): {}", tenant_id, source_type, source_id, str(exc))
        return False


async def search_knowledge(
    tenant_id: UUID,
    query: str,
    limit: int = 5,
    threshold: float = _DEFAULT_THRESHOLD,
) -> list[dict[str, Any]]:
    """Retrieve top-k chunks for *query* via cosine similarity.

    Returns a list of dicts:
      [{"text": str, "source_type": str, "source_id": int, "similarity": float}, ...]

    Returns [] if pgvector is unavailable, query embedding fails, or no results
    exceed *threshold*.
    """
    try:
        from app.routers.v3.knowledge.embedder import embed_text
        from app.db.session import async_session_factory
        from sqlalchemy import text as sql_text

        embedding = await embed_text(query)
        if embedding is None:
            return []

        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"

        async with async_session_factory() as session:
            result = await session.execute(
                sql_text("""
                    SELECT
                        source_type,
                        source_id,
                        chunk_text,
                        1.0 - (embedding <=> CAST(:emb AS vector)) AS similarity
                    FROM knowledge_chunks
                    WHERE tenant_id = :tid
                      AND 1.0 - (embedding <=> CAST(:emb AS vector)) >= :threshold
                    ORDER BY embedding <=> CAST(:emb AS vector)
                    LIMIT :lim
                """),
                {
                    "tid": str(tenant_id),
                    "emb": vec_literal,
                    "threshold": threshold,
                    "lim": limit,
                },
            )
            rows = result.fetchall()

        return [
            {
                "text": row.chunk_text,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.debug("[RAG] search_knowledge failed (tenant={}): {}", tenant_id, str(exc))
        return []


async def delete_chunks(tenant_id: UUID, source_type: str, source_id: int) -> None:
    """Delete all chunks for a specific source (called on FAQ/property delete)."""
    try:
        from app.db.session import async_session_factory
        from sqlalchemy import text as sql_text

        async with async_session_factory() as session:
            await session.execute(
                sql_text("""
                    DELETE FROM knowledge_chunks
                    WHERE tenant_id = :tid
                      AND source_type = :stype
                      AND source_id = :sid
                """),
                {"tid": str(tenant_id), "stype": source_type, "sid": source_id},
            )
            await session.commit()
    except Exception as exc:
        logger.debug("[RAG] delete_chunks failed: {}", str(exc))


def schedule_delete(
    tenant_id: UUID | None,
    source_type: str,
    source_id: int,
) -> None:
    """Fire-and-forget delete — safe to call from sync or async context. Never raises."""
    from app.core.tenancy import resolve_tenant_id

    effective_tid = tenant_id if tenant_id is not None else resolve_tenant_id()
    coro = delete_chunks(effective_tid, source_type, source_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            pass


def schedule_upsert(
    tenant_id: UUID | None,
    source_type: str,
    source_id: int,
    text: str,
) -> None:
    """Fire-and-forget upsert — safe to call from sync or async context.

    Resolves tenant_id to the default if None. Never raises.
    """
    from app.core.tenancy import resolve_tenant_id

    effective_tid = tenant_id if tenant_id is not None else resolve_tenant_id()
    coro = upsert_chunk(effective_tid, source_type, source_id, text)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop — called from a sync thread (e.g. sync admin route).
        # Use run_coroutine_threadsafe to submit to the FastAPI event loop.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            pass


async def reindex_tenant(tenant_id: UUID) -> dict[str, int]:
    """Re-embed all FAQ entries and property descriptions for *tenant_id*.

    Returns {"faqs": n_faqs, "properties": n_props, "errors": n_errors}.
    Useful for initial backfill and after bulk imports. Runs chunked to avoid
    flooding the embedding API.
    """
    from app.db.session import async_session_factory
    from sqlalchemy import text as sql_text

    n_faqs = n_props = n_errors = 0

    # Re-embed FAQ entries
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                sql_text("""
                    SELECT id, question, answer FROM faq_entries
                    WHERE (tenant_id = :tid OR tenant_id IS NULL)
                      AND active = TRUE
                """),
                {"tid": str(tenant_id)},
            )
            faqs = result.fetchall()

        for row in faqs:
            text = f"{row.question}\n{row.answer}"
            ok = await upsert_chunk(tenant_id, "faq", row.id, text)
            if ok:
                n_faqs += 1
            else:
                n_errors += 1
    except Exception as exc:
        logger.warning("[RAG] reindex_tenant FAQs failed: {}", str(exc))

    # Re-embed property descriptions
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                sql_text("""
                    SELECT id, title, description FROM properties
                    WHERE (tenant_id = :tid OR tenant_id IS NULL)
                      AND status = 'available'
                      AND description IS NOT NULL
                      AND description != ''
                """),
                {"tid": str(tenant_id)},
            )
            props = result.fetchall()

        for row in props:
            text = f"{row.title}. {row.description or ''}".strip()
            if len(text) < 10:
                continue
            ok = await upsert_chunk(tenant_id, "property", row.id, text)
            if ok:
                n_props += 1
            else:
                n_errors += 1
    except Exception as exc:
        logger.warning("[RAG] reindex_tenant properties failed: {}", str(exc))

    logger.info(
        "[RAG] reindex_tenant={} done: faqs={} props={} errors={}",
        tenant_id, n_faqs, n_props, n_errors,
    )
    return {"faqs": n_faqs, "properties": n_props, "errors": n_errors}
