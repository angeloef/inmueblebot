"""
Servicio de FAQ (Preguntas Frecuentes).
Maneja el almacenamiento, búsqueda y CRUD de preguntas frecuentes
que el chatbot puede responder automáticamente.
"""
from typing import Optional, List
from loguru import logger
from sqlalchemy import select, or_, and_

from app.db.session import async_session_factory
from app.db.models.faq import FAQ


class FAQService:
    """Servicio asíncrono para gestionar FAQs."""

    def __init__(self):
        pass

    async def search_faqs(self, query: str, limit: int = 5) -> List[FAQ]:
        """
        Busca FAQs que coincidan con la pregunta del usuario.
        Usa búsqueda por palabras clave (ILIKE) sobre question, answer, category y tags.

        Args:
            query: La pregunta del usuario
            limit: Máximo de resultados

        Returns:
            Lista de FAQs ordenadas por relevancia
        """
        if not query or not query.strip():
            return []

        query = query.strip().lower()
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 2]

        async with async_session_factory() as session:
            stmt = (
                select(FAQ)
                .where(FAQ.active == True)
                .order_by(FAQ.order)
                .limit(100)
            )
            result = await session.execute(stmt)
            all_faqs = list(result.scalars().all())

        if not all_faqs:
            return []

        # Score each FAQ by keyword overlap
        scored = []
        for faq in all_faqs:
            score = 0
            # Search in question (highest priority)
            faq_text = (faq.question or "").lower()
            for kw in keywords:
                if kw in faq_text:
                    score += 3
            # Search in answer
            answer_text = (faq.answer or "").lower()
            for kw in keywords:
                if kw in answer_text:
                    score += 2
            # Search in category
            cat_text = (faq.category or "").lower()
            for kw in keywords:
                if kw in cat_text:
                    score += 2
            # Search in tags
            tags_text = " ".join(faq.tags or []).lower()
            for kw in keywords:
                if kw in tags_text:
                    score += 2

            if score > 0:
                scored.append((score, faq))

        # Sort by score descending, then by order
        scored.sort(key=lambda x: (-x[0], x[1].order))
        return [faq for _, faq in scored[:limit]]

    async def get_all_faqs(self, active_only: bool = False) -> List[FAQ]:
        """Obtiene todas las FAQs."""
        async with async_session_factory() as session:
            if active_only:
                stmt = (
                    select(FAQ)
                    .where(FAQ.active == True)
                    .order_by(FAQ.order)
                    .limit(500)
                )
            else:
                stmt = (
                    select(FAQ)
                    .order_by(FAQ.order)
                    .limit(500)
                )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_faq(self, faq_id: int) -> Optional[FAQ]:
        """Obtiene una FAQ por ID."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(FAQ).where(FAQ.id == faq_id)
            )
            return result.scalar_one_or_none()

    async def create_faq(
        self,
        question: str,
        answer: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        order: int = 0,
        active: bool = True
    ) -> FAQ:
        """Crea una nueva FAQ."""
        faq = FAQ(
            question=question,
            answer=answer,
            category=category,
            tags=tags or [],
            order=order,
            active=active,
        )
        async with async_session_factory() as session:
            session.add(faq)
            await session.flush()
            await session.refresh(faq)

        # Fire-and-forget: embed into the knowledge index for RAG (Phase 5)
        if active:
            self._schedule_embed(faq.id, faq.tenant_id, question, answer)

        return faq

    async def update_faq(self, faq_id: int, **kwargs) -> Optional[FAQ]:
        """Actualiza una FAQ existente."""
        from sqlalchemy import update

        async with async_session_factory() as session:
            # Remove None values but respect explicit falsy values like False/0
            safe_kwargs = {k: v for k, v in kwargs.items() if v is not None or k in ('active', 'order')}

            stmt = (
                update(FAQ)
                .where(FAQ.id == faq_id)
                .values(**safe_kwargs)
                .returning(FAQ)
            )
            result = await session.execute(stmt)
            await session.flush()
            faq = result.scalar_one_or_none()

        # Re-embed if question or answer changed and FAQ is still active
        if faq and faq.active:
            self._schedule_embed(faq.id, faq.tenant_id, faq.question, faq.answer)

        return faq

    async def delete_faq(self, faq_id: int) -> bool:
        """Elimina una FAQ."""
        from sqlalchemy import delete

        async with async_session_factory() as session:
            stmt = delete(FAQ).where(FAQ.id == faq_id)
            result = await session.execute(stmt)
            await session.flush()
            deleted = result.rowcount > 0

        # Remove knowledge chunk on delete (best-effort)
        if deleted:
            self._schedule_delete(faq_id)

        return deleted

    # ── RAG embedding helpers (fire-and-forget, never raise) ─────────────────

    @staticmethod
    def _schedule_embed(faq_id: int, tenant_id, question: str, answer: str) -> None:
        """Schedule async embedding without blocking the current request."""
        try:
            from app.routers.v3.knowledge.index import schedule_upsert
            text = f"{question}\n{answer}"
            schedule_upsert(tenant_id, "faq", faq_id, text)
        except Exception:
            pass

    @staticmethod
    def _schedule_delete(faq_id: int) -> None:
        """Schedule async deletion of knowledge chunk."""
        try:
            from app.routers.v3.knowledge.index import schedule_delete
            schedule_delete(None, "faq", faq_id)
        except Exception:
            pass

    async def count_faqs(self) -> int:
        """Cuenta el total de FAQs."""
        from sqlalchemy import func

        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(FAQ)
            )
            return result.scalar_one()


# Singleton
faq_service = FAQService()
