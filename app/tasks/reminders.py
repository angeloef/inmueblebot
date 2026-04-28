"""
Appointment Reminder Tasks.
Handles sending reminders before scheduled appointments.
"""
from datetime import datetime, timezone, timedelta
from celery import shared_task
from loguru import logger
from uuid import UUID
import asyncio


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_appointment_reminder(self, appointment_id: str):
    """
    Envía recordatorio de cita al usuario.
    
    Args:
        appointment_id: ID de la cita
    """
    from app.services.notification_service import notification_service
    from app.services.appointment_service import appointment_service
    from app.services.property_service import property_service
    from app.db.repository import UserRepository
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.config import get_settings
    
    try:
        logger.info(f"Enviando recordatorio para cita {appointment_id}")
        
        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async def _send():
            async with session_factory() as db:
                apt_uuid = UUID(appointment_id)
                appointment = await appointment_service.get_appointment(apt_uuid)
                
                if not appointment:
                    logger.warning(f"Cita {appointment_id} no encontrada")
                    return
                
                if appointment.status == "cancelled":
                    logger.info(f"Cita {appointment_id} cancelada, omitiendo recordatorio")
                    return
                
                now = datetime.now(timezone)
                time_until = appointment.start_time - now
                hours_until = time_until.total_seconds() / 3600
                
                if hours_until <= 0:
                    logger.info(f"Cita {appointment_id} ya pasó, omitiendo")
                    return
                
                user_repo = UserRepository(db)
                user = await user_repo.get_by_id(appointment.user_id)
                
                if not user:
                    logger.error(f"Usuario {appointment.user_id} no encontrado")
                    return
                
                property_obj = await property_service.get_property_details(appointment.property_id)
                prop_title = property_obj.title if property_obj else "Propiedad"
                
                date_str = appointment.start_time.strftime("%d/%m/%Y")
                time_str = appointment.start_time.strftime("%H:%M")
                
                if hours_until <= 2:
                    message = (
                        f"⏰ *Recordatorio: Tu visita es en 2 horas!*\n\n"
                        f"📆 *Fecha:* {date_str}\n"
                        f"⏰ *Hora:* {time_str}\n"
                        f"🏠 *Propiedad:* {prop_title}\n\n"
                        f"¿Seguimos en contacto? ¡Te esperamos! 😊"
                    )
                else:
                    message = (
                        f"📅 *Recordatorio: Tu visita es mañana!*\n\n"
                        f"📆 *Fecha:* {date_str}\n"
                        f"⏰ *Hora:* {time_str}\n"
                        f"🏠 *Propiedad:* {prop_title}\n\n"
                        f"¿Tienes alguna duda? Estamos para ayudarte."
                    )
                
                await notification_service.send_whatsapp_message(
                    phone=user.phone,
                    message=message
                )
                
                logger.info(f"Recordatorio enviado para cita {appointment_id} a {user.phone}")
        
        asyncio.run(_send())
            
    except Exception as e:
        logger.error(f"Error enviando recordatorio: {e}")
        raise self.retry(exc=e)


@shared_task
def check_upcoming_appointments():
    """
    Tarea periódica que verifica citas próximas.
    Se ejecuta cada 30 minutos.
    """
    logger.info("Verificando citas próximas para recordatorios...")
    
    from app.db.models import Appointment
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.config import get_settings
    
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def _check():
        now = datetime.now(timezone)
        check_window = now + timedelta(hours=26)
        
        async with session_factory() as db:
            result = await db.execute(
                select(Appointment).where(
                    Appointment.start_time <= check_window,
                    Appointment.start_time >= now,
                    Appointment.status == "confirmed"
                )
            )
            appointments = result.scalars().all()
            
            logger.info(f"Verificación completada. Citas próximas encontradas: {len(appointments)}")
    
    asyncio.run(_check())