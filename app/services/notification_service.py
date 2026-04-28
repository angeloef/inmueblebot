"""
Notification Service.
Handles sending notifications via WhatsApp and other channels.
"""
from typing import Optional
from datetime import datetime, timezone
from loguru import logger
from uuid import uuid4

from app.db.models import Message
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings


class NotificationService:
    """
    Servicio de notificaciones.
    
    Currently implements:
    - WhatsApp message logging and DB storage
    
    TODO: Integrate with Meta WhatsApp Business API
    - Use WhatsApp Cloud API: https://developers.facebook.com/docs/whatsapp
    - Template messages for proactive notifications
    - Media attachments
    """
    
    def __init__(self):
        settings = get_settings()
        self._engine = create_async_engine(settings.DATABASE_URL, echo=False)
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
    
    async def send_whatsapp_message(
        self,
        phone: str,
        message: str,
        media_url: Optional[str] = None
    ) -> bool:
        """
        Envía un mensaje de WhatsApp al usuario.
        
        Args:
            phone: Número de teléfono del destinatario
            message: Contenido del mensaje
            media_url: URL de imagen/video opcional
        
        Returns:
            True si se envió correctamente
        
        Note:
            Esta es una implementación placeholder que:
            1. Registra el mensaje en la base de datos
            2. Loguea el mensaje para debugging
            
            Para integración real con WhatsApp:
            1. Usar WhatsApp Cloud API (POST /v17.0/{PHONE_NUMBER_ID}/messages)
            2. Autenticar con access token de Meta
            3. Usar templates pre-aprobados para mensajes proactivos
        """
        try:
            logger.info(f"Enviando WhatsApp a {phone}: {message[:50]}...")
            
            async with self._session_factory() as db:
                db_message = Message(
                    id=uuid4(),
                    user_id=None,
                    phone=phone,
                    role="assistant",
                    content=message,
                    media_url=media_url,
                    created_at=datetime.now(timezone)
                )
                
                db.add(db_message)
                await db.commit()
            
            logger.info(f"Mensaje guardado en DB para {phone}")
            
            # TODO: WhatsApp API Integration
            # try:
            #     async with httpx.AsyncClient() as client:
            #         response = await client.post(
            #             f"https://graph.facebook.com/v17.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
            #             headers={
            #                 "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            #                 "Content-Type": "application/json"
            #             },
            #             json={
            #                 "messaging_product": "whatsapp",
            #                 "to": phone,
            #                 "type": "text",
            #                 "text": {"body": message}
            #             }
            #         )
            #         response.raise_for_status()
            #         logger.info(f"WhatsApp message sent via API")
            # except Exception as e:
            #     logger.error(f"WhatsApp API error: {e}")
            #     raise
            
            return True
            
        except Exception as e:
            logger.error(f"Error enviando mensaje a {phone}: {e}")
            raise
    
    async def send_appointment_confirmation(
        self,
        phone: str,
        appointment_date: datetime,
        property_title: str
    ) -> bool:
        """Envía confirmación de cita."""
        date_str = appointment_date.strftime("%d/%m/%Y a las %H:%M")
        
        message = (
            f"📅 *Confirmación de Cita*"
            f"\n\n"
            f"Tu visita ha sido confirmada:"
            f"\n📆 {date_str}"
            f"\n🏠 {property_title}"
            f"\n\n"
            f"¡Te esperamos! 😊"
        )
        
        return await self.send_whatsapp_message(phone, message)
    
    async def send_reminder(
        self,
        phone: str,
        hours_until: int,
        property_title: str
    ) -> bool:
        """Envía recordatorio de cita."""
        if hours_until <= 2:
            message = f"⏰ *Tu visita es en 2 horas!*\n\n🏠 {property_title}\n\n¡Te esperamos!"
        else:
            message = f"📅 *Recordatorio: Tu visita es mañana*\n\n🏠 {property_title}\n\n¿Necesitas algo?"
        
        return await self.send_whatsapp_message(phone, message)
    
    async def send_followup(
        self,
        phone: str,
        property_title: Optional[str] = None
    ) -> bool:
        """Envía mensaje de seguimiento."""
        if property_title:
            message = (
                f"👋 *Hola!* ¿Qué tal con la propiedad {property_title}?"
                f"\n\n¿Tenés alguna duda? ¿Querés agendar una visita?"
            )
        else:
            message = (
                f"👋 *Hola!* ¿Cómo vas con la búsqueda de propiedades?"
                f"\n\n¿Puedo ayudarte en algo?"
            )
        
        return await self.send_whatsapp_message(phone, message)


notification_service = NotificationService()