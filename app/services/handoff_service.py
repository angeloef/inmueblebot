"""
Human Handoff Service.
Handles transferring conversations to human agents.
"""
from typing import Optional
from datetime import datetime, timezone
from uuid import uuid4
from loguru import logger

from app.agents.llm_router import llm_router
from app.core.state_machine import state_machine, ConversationStateEnum
from app.db.models import User
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings


class HandoffService:
    """
    Servicio para transferir conversaciones a agentes humanos.
    
    Funcionalidades:
    - Genera resúmenes de conversación usando LLM
    - Notifica a agentes humanos (placeholder)
    - Guarda contexto para el agente humano
    """
    
    def __init__(self):
        pass
    
    def _get_engine(self):
        """Lazy initialization of database engine."""
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.core.config import get_settings
        
        settings = get_settings()
        return create_async_engine(settings.DATABASE_URL, echo=False)
    
    def _get_session_factory(self, engine):
        """Get session factory for given engine."""
        from sqlalchemy.orm import sessionmaker
        return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def generate_conversation_summary(self, phone: str) -> str:
        """
        Genera un resumen conciso de la conversación para un agente humano.
        
        Args:
            phone: Número de teléfono del usuario
        
        Returns:
            Resumen formateado de la conversación
        """
        from app.core.memory import memory_manager
        
        try:
            logger.info(f"Generando resumen de conversación para {phone}")
            
            context = await memory_manager.get_user_context(phone)
            recent_messages = context.get("recent_messages", [])[-10:]
            preferences = context.get("preferences", {})
            lead_score = context.get("lead_score", 0)
            current_state = context.get("current_state", "unknown")
            
            user_info = preferences.get("name", "Cliente")
            location = preferences.get("location_preferences", "No especificada")
            budget = preferences.get("budget_max")
            property_type = preferences.get("property_type", "casa")
            bedrooms = preferences.get("bedrooms")
            
            budget_str = f"${budget:,} USD" if budget else "No especificado"
            
            conversation_history = "\n".join([
                f"{'Usuario' if m.get('role') == 'user' else 'Bot'}: {m.get('content', '')[:100]}"
                for m in recent_messages[-5:]
            ])
            
            prompt = f"""Genera un resumen profesional y conciso de esta conversación de bienes raíces para un agente humano.

Información del cliente:
- Nombre: {user_info}
- Teléfono: {phone}
- Ubicación de interés: {location}
- Presupuesto: {budget_str}
- Tipo de propiedad: {property_type}
- Dormitorios: {bedrooms if bedrooms else 'No especificados'}
- Lead score: {lead_score} puntos
- Estado actual: {current_state}

Historial reciente:
{conversation_history}

Genera un resumen en español que incluya:
1. Perfil del cliente (qué busca, presupuesto)
2. Historial relevante de la conversación
3. Próximo paso recomendado para el agente humano

Sé conciso pero útil. Máximo 200 palabras."""

            summary = await llm_router.chat(
                message=prompt,
                system_prompt="Eres un asistente que genera resúmenes de conversaciones para agentes de bienes raíces. Sé conciso y profesional.",
                temperature=0.5,
                max_tokens=500
            )
            
            logger.info(f"Resumen generado para {phone}")
            return summary
            
        except Exception as e:
            logger.error(f"Error generando resumen: {e}")
            return f"Error al generar resumen. Teléfono: {phone}."
    
    async def trigger_handoff(
        self,
        phone: str,
        reason: str = "user_requested"
    ) -> dict:
        """
        Inicia la transferencia a un agente humano.
        
        Args:
            phone: Número de teléfono del usuario
            reason: Razón del handoff (user_requested, complex_query, etc.)
        
        Returns:
            Dict con resultado del handoff
        """
        from app.core.memory import memory_manager
        
        try:
            logger.info(f"Iniciando handoff para {phone}, razón: {reason}")
            
            summary = await self.generate_conversation_summary(phone)
            
            await memory_manager.update_user_preferences(phone, {
                "handoff_reason": reason,
                "handoff_summary": summary,
                "handoff_requested_at": datetime.now(timezone.utc).isoformat()
            })
            
            await state_machine.set_state(phone, ConversationStateEnum.HUMAN_ASSISTANCE.value)
            
            await self._notify_admin(phone, summary, reason)
            
            logger.info(f"Handoff completado para {phone}")
            
            return {
                "success": True,
                "phone": phone,
                "reason": reason,
                "summary": summary,
                "message": "El agente humano te contactará pronto. ¿Hay algo más en lo que pueda ayudarte?"
            }
            
        except Exception as e:
            logger.error(f"Error en handoff: {e}")
            return {
                "success": False,
                "phone": phone,
                "error": str(e)
            }
    
    async def _notify_admin(self, phone: str, summary: str, reason: str):
        """
        Notifica al administrador sobre el handoff.
        
        TODO: Integrar con WhatsApp grupo de agentes o email/Slack.
        """
        logger.info(f"🔔 NOTIFICACIÓN DE HANDOFF")
        logger.info(f"Teléfono: {phone}")
        logger.info(f"Razón: {reason}")
        logger.info(f"Resumen:\n{summary}")
        
        # TODO: Implementar notificación real
        # - WhatsApp a grupo de agentes
        # - Email a agentes
        # - Slack webhook
    
    async def get_handoff_status(self, phone: str) -> Optional[dict]:
        """Obtiene el estado de handoff del usuario."""
        from app.core.memory import memory_manager
        
        try:
            context = await memory_manager.get_user_context(phone)
            prefs = context.get("preferences", {})
            
            if prefs.get("handoff_requested_at"):
                return {
                    "status": "handed_off",
                    "requested_at": prefs.get("handoff_requested_at"),
                    "reason": prefs.get("handoff_reason", "unknown"),
                    "summary": prefs.get("handoff_summary", "")
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo estado de handoff: {e}")
            return None


handoff_service = HandoffService()