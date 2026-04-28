"""
Lead Scoring Tasks.
Handles automatic lead score updates based on user actions.
"""
from datetime import datetime, timezone, timedelta
from celery_app import celery_app
from loguru import logger
from uuid import UUID


# Lead scoring rules
LEAD_SCORE_RULES = {
    "property_search": 10,
    "view_details": 20,
    "book_appointment": 30,
    "property_visit": 50,  # Manual update later
    "signing": 100,  # Manual update
}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def update_lead_score(self, user_id: str, action: str):
    """
    Actualiza el lead score del usuario basado en una acción.
    
    Args:
        user_id: ID del usuario
        action: Acción realizada (property_search, view_details, book_appointment, etc.)
    """
    from app.db.repository import UserRepository
    from app.db.repository.database import SessionLocal
    
    try:
        score_increase = LEAD_SCORE_RULES.get(action, 0)
        
        if score_increase == 0:
            logger.warning(f"Acción desconocida: {action}")
            return
        
        logger.info(f"Actualizando lead score para usuario {user_id}: +{score_increase} por {action}")
        
        user_uuid = UUID(user_id)
        
        db = SessionLocal()
        try:
            user_repo = UserRepository(db)
            user = user_repo.get_by_id(user_uuid)
            
            if not user:
                logger.warning(f"Usuario {user_id} no encontrado")
                return
            
            user.lead_score = (user.lead_score or 0) + score_increase
            user.last_interaction = datetime.now(timezone)
            
            db.commit()
            
            logger.info(f"Lead score actualizado: {user.lead_score} puntos para usuario {user_id}")
            
            if user.lead_score >= 100:
                logger.info(f"Usuario {user_id} es un lead caliente (score: {user.lead_score})")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error actualizando lead score: {e}")
        raise self.retry(exc=e)


@celery_app.task
def update_all_lead_scores():
    """
    Tarea periódica que ejecuta scoring nocturno.
    Actualiza scores basados en actividad reciente.
    Se ejecuta diariamente a las 2 AM.
    """
    from app.db.models import User, Message, Appointment
    from sqlalchemy import select, func, and_
    from app.db.repository.database import SessionLocal
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.config import get_settings
    
    logger.info("Ejecutando scoring nocturno de leads...")
    
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def update():
        async with session_factory() as db:
            result = await db.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()
            
            updated = 0
            for user in users:
                try:
                    search_result = await db.execute(
                        select(func.count(Message.id)).where(
                            and_(
                                Message.user_id == user.id,
                                Message.role == "user"
                            )
                        )
                    )
                    message_count = search_result.scalar() or 0
                    
                    apt_result = await db.execute(
                        select(func.count(Appointment.id)).where(
                            and_(
                                Appointment.user_id == user.id,
                                Appointment.status == "confirmed"
                            )
                        )
                    )
                    appointment_count = apt_result.scalar() or 0
                    
                    base_score = min(message_count * 5, 50)
                    appointment_score = appointment_count * 30
                    
                    new_score = base_score + appointment_score
                    
                    if user.lead_score != new_score:
                        user.lead_score = new_score
                        updated += 1
                        logger.debug(f"Usuario {user.id}: score actualizado a {new_score}")
                    
                except Exception as e:
                    logger.error(f"Error actualizando usuario {user.id}: {e}")
            
            db.commit()
            logger.info(f"Scoring nocturno completado: {updated} usuarios actualizados")
    
    import asyncio
    asyncio.run(update())


@celery_app.task
def update_user_after_property_search(user_id: str):
    """Helper task para actualizar después de búsqueda."""
    update_lead_score.apply_async(args=[user_id, "property_search"])


@celery_app.task
def update_user_after_view_details(user_id: str):
    """Helper task para actualizar después de ver detalles."""
    update_lead_score.apply_async(args=[user_id, "view_details"])


@celery_app.task
def update_user_after_appointment(user_id: str):
    """Helper task para actualizar después de agendar cita."""
    update_lead_score.apply_async(args=[user_id, "book_appointment"])