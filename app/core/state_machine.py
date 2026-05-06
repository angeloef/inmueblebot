"""
Máquina de estados finitos para controlar el flujo de conversación.

Estados:
- idle: El usuario no ha iniciado conversación o está inactivo
- qualifying: Recolectando información del usuario (nombre, presupuesto, ubicación)
- searching: El usuario está buscando propiedades
- viewing_property: El usuario está viendo detalles de una propiedad específica
- booking: Agendando una cita para visitar la propiedad
- completed: La conversación terminó exitosamente (cita agendada o usuario satisfecho)
- handoff: Escalando a un agente humano

Transiciones válidas:
- idle -> qualifying: Usuario envía mensaje inicial
- idle -> searching: Usuario busca propiedades directamente
- qualifying -> searching: Usuario proporciona suficiente información
- searching -> viewing_property: Usuario selecciona una propiedad
- searching -> qualifying: Usuario proporciona más detalles
- viewing_property -> booking: Usuario quiere agendar visita
- viewing_property -> searching: Usuario vuelve a buscar
- booking -> completed: Cita confirmada
- booking -> viewing_property: Usuario cancela agendamiento
- * -> handoff: Usuario pide hablar con humano
- * -> idle: Timeout o conversación inactiva

Con soporte para:
- Reconexión automática con exponential backoff
- Degradación graceful si Redis no está disponible
"""
import asyncio
from enum import Enum
from typing import Optional, Callable
from datetime import datetime, timedelta
import redis.asyncio as redis
import json
from loguru import logger

from app.core.config import get_settings


class ConversationStateEnum(str, Enum):
    """Estados posibles de la conversación."""
    IDLE = "idle"
    QUALIFYING = "qualifying"
    SEARCHING = "searching"
    VIEWING_PROPERTY = "viewing_property"
    BOOKING = "booking"
    COMPLETED = "completed"
    HANDOFF = "handoff"
    HUMAN_ASSISTANCE = "human_assistance"


class TransitionError(Exception):
    """Error personalizado para transiciones inválidas."""
    pass


class ConversationState:
    """
    Gestor de estado de conversación con persistencia Redis + PostgreSQL.
    """
    
    STATE_TTL = 1800  # 30 minutes
    
    VALID_TRANSITIONS = {
        ConversationStateEnum.IDLE: [
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.QUALIFYING: [
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.SEARCHING: [
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.VIEWING_PROPERTY: [
            ConversationStateEnum.BOOKING,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.BOOKING: [
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.IDLE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.COMPLETED: [
            ConversationStateEnum.IDLE,
            ConversationStateEnum.SEARCHING,
        ],
        ConversationStateEnum.HANDOFF: [
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.HUMAN_ASSISTANCE: [
            ConversationStateEnum.IDLE,
        ],
    }
    
    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._redis_url = settings.resolve_redis_url()
        self._redis_available = False
        self._connection_tested = False
        self._max_retries = 5
        self._retry_delay = 0.5
    
    async def check_health(self) -> dict:
        """Verifica el estado de Redis."""
        try:
            r = await self._get_redis_with_retry()
            await r.ping()
            self._redis_available = True
            self._connection_tested = True
            return {"status": "healthy", "redis": "connected"}
        except Exception as e:
            self._redis_available = False
            self._connection_tested = True
            return {"status": "unavailable", "error": str(e)[:100]}
    
    async def _get_redis_with_retry(self) -> redis.Redis:
        """Obtiene cliente Redis con reintentos y fast-fail."""
        if self._connection_tested and not self._redis_available:
            raise ConnectionError("Redis previously marked unavailable")

        last_error = None

        for attempt in range(self._max_retries):
            try:
                if self._redis is None:
                    self._redis = redis.from_url(
                        self._redis_url,
                        decode_responses=True,
                        socket_connect_timeout=10,
                        socket_timeout=15,
                    )

                await self._redis.ping()
                self._redis_available = True
                self._connection_tested = True
                return self._redis

            except Exception as e:
                last_error = e
                self._redis_available = False
                self._connection_tested = True
                delay = self._retry_delay * (2 ** attempt)
                logger.warning(f"[StateMachine] Redis retry {attempt + 1}/{self._max_retries}: {e}")
                await asyncio.sleep(delay)

        logger.error(f"[StateMachine] Redis no disponible después de {self._max_retries} intentos")
        raise last_error
    
    def _is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Verifica si la transición es válida."""
        try:
            from_enum = ConversationStateEnum(from_state)
            to_enum = ConversationStateEnum(to_state)
            
            allowed = self.VALID_TRANSITIONS.get(from_enum, [])
            return to_enum in allowed
        except ValueError:
            return to_state == ConversationStateEnum.IDLE.value
    
    async def get_state(self, phone: str) -> str:
        """Obtiene el estado actual de la conversación del usuario."""
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:state"
            state = await r.get(key)
            if state:
                return state
            return ConversationStateEnum.IDLE.value
        except Exception as e:
            logger.warning(f"Redis no disponible para estado: {e}")
            return ConversationStateEnum.IDLE.value
    
    async def set_state(
        self,
        phone: str,
        new_state: str,
        context: Optional[dict] = None,
        allow_invalid: bool = False
    ) -> bool:
        """Establece un nuevo estado para la conversación."""
        current_state = await self.get_state(phone)
        
        if not allow_invalid and not self._is_valid_transition(current_state, new_state):
            error_msg = f"Transición inválida: {current_state} -> {new_state}"
            logger.warning(f"{error_msg} para {phone}")
            raise TransitionError(error_msg)
        
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:state"
            
            await r.setex(key, self.STATE_TTL, new_state)
            
            if context:
                context_key = f"user:{phone}:state_context"
                context["state"] = new_state
                context["updated_at"] = datetime.utcnow().isoformat()
                await r.setex(context_key, self.STATE_TTL, json.dumps(context, default=str))
            
            logger.info(f"Estado cambiado para {phone}: {current_state} -> {new_state}")
            return True
        except Exception as e:
            logger.warning(f"Redis no disponible para set_state: {e}")
            return True
    
    async def get_state_context(self, phone: str) -> Optional[dict]:
        """Obtiene el contexto adicional del estado actual."""
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:state_context"
            data = await r.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Redis no disponible para get_state_context: {e}")
            return None
    
    async def reset_state(self, phone: str) -> bool:
        """Resetea el estado a idle y limpia el contexto."""
        try:
            r = await self._get_redis_with_retry()
            keys = [
                f"user:{phone}:state",
                f"user:{phone}:state_context",
            ]
            await r.delete(*keys)
            
            logger.info(f"Estado reseteado para {phone}")
            return True
        except Exception as e:
            logger.error(f"Error al resetear estado de {phone}: {e}")
            return False
    
    async def get_previous_state(self, phone: str) -> str:
        """Obtiene el estado anterior de la conversación."""
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:previous_state"
            state = await r.get(key)
            if state:
                return state
            return ConversationStateEnum.IDLE.value
        except Exception as e:
            logger.warning(f"Redis no disponible para previous_state: {e}")
            return ConversationStateEnum.IDLE.value

    async def close(self):
        """Cierra conexión Redis."""
        if self._redis:
            await self._redis.close()


state_machine = ConversationState()