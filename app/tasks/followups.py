"""
Follow-up Automation Tasks.
Handles sending follow-up messages to users.
"""
from datetime import datetime, timezone, timedelta
from celery_app import celery_app
from loguru import logger
from uuid import UUID


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def send_property_followup(self, user_id: str, property_id: str):
    """
    Envía seguimiento 48 horas después de mostrar una propiedad.
    
    Args:
        user_id: ID del usuario
        property_id: ID de la propiedad
    """
    from app.services.notification_service import notification_service
    from app.services.property_service import property_service
    from app.db.repository import UserRepository
    from app.db.repository.database import SessionLocal
    
    try:
        logger.info(f"Enviando seguimiento de propiedad {property_id} a usuario {user_id}")
        
        user_uuid = UUID(user_id)
        prop_uuid = UUID(property_id)
        
        db = SessionLocal()
        try:
            user_repo = UserRepository(db)
            user = user_repo.get_by_id(user_uuid)
            
            if not user:
                logger.warning(f"Usuario {user_id} no encontrado")
                return
            
            property_obj = await property_service.get_property_details(prop_uuid)
            prop_title = property_obj.title if property_obj else "esa propiedad"
            prop_location = property_obj.location if property_obj else ""
            
            message = (
                f"¡Hola! 👋"
                f"\n\n"
                f"¿Qué tal te fue viendo la propiedad *{prop_title}*?"
                f"\n"
                f"📍 {prop_location}"
                f"\n\n"
                f"¿Te gustaría agendar una visita formal? "
                f"¿O tienes alguna duda sobre la propiedad?"
                f"\n\n"
                f"Estoy aquí para ayudarte! 😊"
            )
            
            await notification_service.send_whatsapp_message(
                phone=user.phone,
                message=message
            )
            
            logger.info(f"Seguimiento enviado a {user.phone} por propiedad {property_id}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error en seguimiento de propiedad: {e}")
        raise self.retry(exc=e)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def send_inactive_user_followup(self, user_id: str):
    """
    Envía seguimiento a usuarios inactivos después de 7 días.
    
    Args:
        user_id: ID del usuario
    """
    from app.services.notification_service import notification_service
    from app.db.repository import UserRepository
    from app.db.repository.database import SessionLocal
    
    try:
        logger.info(f"Enviando seguimiento a usuario inactivo {user_id}")
        
        user_uuid = UUID(user_id)
        
        db = SessionLocal()
        try:
            user_repo = UserRepository(db)
            user = user_repo.get_by_id(user_uuid)
            
            if not user:
                logger.warning(f"Usuario {user_id} no encontrado")
                return
            
            message = (
                f"¡Hola! 👋"
                f"\n\n"
                f"Te extrañamos por aquí! 😊"
                f"\n"
                f"¿Seguís buscando propiedades? "
                f"Si necesitas ayuda, aquí estoy para asistirte."
                f"\n\n"
                f"Tenemos nuevas propiedades en Asunción, Posadas y más zonas. "
                f"¿Querés que te muestre algunas opciones?"
            )
            
            await notification_service.send_whatsapp_message(
                phone=user.phone,
                message=message
            )
            
            logger.info(f"Seguimiento inactivo enviado a {user.phone}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error en seguimiento inactivo: {e}")
        raise self.retry(exc=e)


@celery_app.task
def send_property_followups():
    """
    Tarea periódica que busca propiedades vistas hace 48 horas sin cita.
    Se ejecuta diariamente a las 10 AM.
    """
    from app.db.models import User
    from sqlalchemy import select, and_
    from app.db.repository.database import SessionLocal
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.config import get_settings
    
    logger.info("Buscando propiedades vistas hace 48 horas...")
    
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def check():
        cutoff = datetime.now(timezone) - timedelta(hours=52)
        inactive_cutoff = datetime.now(timezone) - timedelta(days=7)
        
        async with session_factory() as db:
            result = await db.execute(
                select(User).where(
                    User.last_interaction != None,
                    User.last_interaction <= cutoff,
                    User.last_interaction >= inactive_cutoff
                )
            )
            users = result.scalars().all()
            
            for user in users:
                if user.lead_score and user.lead_score > 30:
                    send_inactive_user_followup.apply_async(args=[str(user.id)])
                    logger.info(f"Programado seguimiento para usuario {user.id}")
            
            logger.info(f"Seguimientos de propiedades procesados: {len(users)}")
    
    import asyncio
    asyncio.run(check())


@celery_app.task
def send_inactive_user_followups():
    """
    Tarea periódica que busca usuarios sin interacción en 7 días.
    Se ejecuta diariamente a las 11 AM.
    """
    from app.db.models import User
    from sqlalchemy import select
    from app.db.repository.database import SessionLocal
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.config import get_settings
    
    logger.info("Buscando usuarios inactivos...")
    
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def check():
        inactive_cutoff = datetime.now(timezone) - timedelta(days=7)
        
        async with session_factory() as db:
            result = await db.execute(
                select(User).where(
                    User.last_interaction <= inactive_cutoff
                )
            )
            users = result.scalars().all()
            
            for user in users:
                send_inactive_user_followup.apply_async(args=[str(user.id)])
                logger.info(f"Programado seguimiento para usuario inactivo {user.id}")
            
            logger.info(f"Usuarios inactivos encontrados: {len(users)}")
    
    import asyncio
    asyncio.run(check())