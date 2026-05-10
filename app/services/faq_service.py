"""
Servicio de FAQ (Preguntas Frecuentes).
Maneja la búsqueda y gestión de entradas de FAQ para el bot.
"""
from typing import Optional, List
from loguru import logger
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_factory
from app.db.models.faq import FAQ


class FAQService:
    """Servicio asíncrono para gestionar preguntas frecuentes."""

    def __init__(self):
        pass

    def _get_session(self) -> AsyncSession:
        return async_session_factory()

    async def search_faqs(
        self,
        query: str,
        category: str = None,
        limit: int = 5,
    ) -> List[FAQ]:
        """
        Busca entradas de FAQ por texto en question, answer y tags.
        
        Args:
            query: Texto de búsqueda (ej: "horarios", "financiación")
            category: Filtrar por categoría (opcional)
            limit: Máximo de resultados
        
        Returns:
            Lista de entradas FAQ que coinciden
        """
        db = self._get_session()
        try:
            stmt = select(FAQ).where(FAQ.active == True)

            if query:
                like_pattern = f"%{query}%"
                stmt = stmt.where(
                    or_(
                        FAQ.question.ilike(like_pattern),
                        FAQ.answer.ilike(like_pattern),
                        FAQ.tags.any(query, operator=lambda col, op: col.ilike(like_pattern)),
                    )
                )

            if category:
                stmt = stmt.where(FAQ.category == category)

            stmt = stmt.order_by(FAQ.order.asc(), FAQ.id.asc()).limit(limit)

            result = await db.execute(stmt)
            entries = list(result.scalars().all())

            logger.info(f"[FAQ] search_faqs(query='{query}', category={category}) → {len(entries)} matches")
            return entries

        except Exception as e:
            logger.error(f"[FAQ] Error searching FAQs: {e}")
            return []
        finally:
            await db.close()

    async def get_faq_by_id(self, faq_id: int) -> Optional[FAQ]:
        """Obtiene una entrada de FAQ por ID."""
        db = self._get_session()
        try:
            result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
            return result.scalar_one_or_none()
        finally:
            await db.close()

    async def get_all_faqs(self, active_only: bool = True, category: str = None) -> List[FAQ]:
        """Obtiene todas las entradas de FAQ."""
        db = self._get_session()
        try:
            stmt = select(FAQ)
            if active_only:
                stmt = stmt.where(FAQ.active == True)
            if category:
                stmt = stmt.where(FAQ.category == category)
            stmt = stmt.order_by(FAQ.order.asc(), FAQ.id.asc())
            result = await db.execute(stmt)
            return list(result.scalars().all())
        finally:
            await db.close()

    async def get_categories(self) -> List[str]:
        """Obtiene todas las categorías de FAQ distintas."""
        db = self._get_session()
        try:
            result = await db.execute(
                select(FAQ.category)
                .where(FAQ.category.isnot(None))
                .where(FAQ.active == True)
                .distinct()
                .order_by(FAQ.category)
            )
            return [row[0] for row in result.all()]
        finally:
            await db.close()


# Singleton
faq_service = FAQService()
