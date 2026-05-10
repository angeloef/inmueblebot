"""
Gestión de memoria híbrida: Redis (corto plazo) + PostgreSQL (largo plazo).

Redis store:
- user:{phone}:context    -> JSON (current conversation state, last search criteria)
- user:{phone}:messages   -> JSON (últimos 20 mensajes)
- user:{phone}:summary    -> string (resumen de conversación, actualizable por LLM)

PostgreSQL store:
- Tabla users: location_preferences, property_type, budget_min, budget_max, lead_score, last_interaction

Esta memoria se usará para:
1. Mantener contexto de la conversación actual (Redis)
2. Persistir preferencias del usuario (PostgreSQL)
3. Resumir conversaciones previas para contexto del LLM (MiniMax)

Con soporte para:
- Reconexión automática con exponential backoff
- Degradación graceful si Redis no está disponible
- Health check para monitoreo
"""
import asyncio
import json
from typing import Optional, Dict, List
from datetime import datetime
import redis.asyncio as redis
from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import User
from app.db.repository import UserRepository


class MemoryManager:
    """
    Gestor de memoria híbrida para el bot.
    Combina Redis (corto plazo) + PostgreSQL (largo plazo).
    Usa Async Connection Pool para mejor rendimiento.
    """
    
    CONTEXT_TTL = 86400
    MESSAGES_TTL = 86400
    MAX_MESSAGES = 20
    
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0
    
    def __init__(self):
        settings = get_settings()
        self._pool: Optional[redis.ConnectionPool] = None
        self._redis: Optional[redis.Redis] = None
        self._redis_url = settings.resolve_redis_url()
        self._redis_available = False
        self._connection_tested = False
        self._degraded_logged = False

        # In-memory fallback stores — used when Redis is down so the
        # user never loses their conversation context even during a
        # Redis restart or transient outage.
        self._fallback_context: Dict[str, dict] = {}
        self._fallback_messages: Dict[str, list] = {}
    
    async def check_health(self) -> dict:
        """
        Health check para Redis.
        Returns: {"status": "healthy"|"degraded", "redis": "connected"|"unavailable"}
        """
        try:
            r = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=15,
            )
            await r.ping()
            await r.aclose()
            self._redis_available = True
            self._connection_tested = True
            return {"status": "healthy", "redis": "connected"}
        except Exception as e:
            self._redis_available = False
            self._connection_tested = True
            if not self._degraded_logged:
                logger.warning(f"[Memory] REDIS DOWN: Using temporary local cache ({e})")
                self._degraded_logged = True
            return {"status": "degraded", "redis": "unavailable", "error": str(e)[:100]}
    
    async def _get_connection_pool(self) -> redis.ConnectionPool:
        """Obtiene o crea el connection pool de Redis."""
        if self._pool is None:
            self._pool = redis.ConnectionPool.from_url(
                self._redis_url,
                decode_responses=True,
                max_connections=10,
                socket_connect_timeout=10,
                socket_timeout=15,
                retry_on_timeout=True,
            )
        return self._pool
    
    async def _get_redis(self) -> redis.Redis:
        """Obtiene cliente Redis desde el connection pool."""
        pool = await self._get_connection_pool()
        return redis.Redis(connection_pool=pool)
    
    async def _get_redis_with_retry(self) -> redis.Redis:
        """Obtiene cliente Redis con reintentos y exponential backoff.
        
        Once Redis is confirmed unreachable, subsequent calls fail instantly
        to avoid adding latency on every message.
        """
        if self._connection_tested and not self._redis_available:
            raise ConnectionError("Redis previously marked unavailable")

        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                r = await self._get_redis()
                await r.ping()
                self._redis_available = True
                if not self._connection_tested:
                    logger.info(f"[Memory] Redis conectado: {self._redis_url}")
                    self._connection_tested = True
                    self._degraded_logged = False
                return r

            except Exception as e:
                last_error = e
                self._redis_available = False
                self._connection_tested = True
                delay = self.RETRY_BASE_DELAY * (2 ** attempt)

                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"[Memory] Redis retry {attempt + 1}/{self.MAX_RETRIES}: {e}")
                    await asyncio.sleep(delay)
                else:
                    if not self._degraded_logged:
                        logger.warning(f"[Memory] REDIS DOWN: Using temporary local cache")
                        self._degraded_logged = True

        logger.error(f"[Memory] Redis unavailable after {self.MAX_RETRIES} attempts")
        raise last_error
    
    # =========================================================================
    # MÉTODOS DE CONTEXTO (REDIS - CORTO PLAZO)
    # =========================================================================
    
    async def get_user_context(self, phone: str) -> dict:
        """
        Obtiene el contexto actual del usuario desde Redis.
        Si Redis no está disponible, retorna contexto desde fallback en memoria.
        """
        _DEFAULT = {
            "current_state": "idle",
            "last_search_criteria": None,
            "selected_property_id": None,
            "conversation_stage": "new",
            "pending_scheduling_info": None,
        }

        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:context"
            data = await r.get(key)
            if data:
                context = json.loads(data)
                # Sync fallback cache so it's always up to date
                self._fallback_context[phone] = context
                return context
            return _DEFAULT
        except Exception as e:
            logger.debug(f"[Memory] Redis unavailable, using fallback context: {e}")
            return self._fallback_context.get(phone, _DEFAULT)
    
    async def save_user_context(self, phone: str, context: dict) -> bool:
        """
        Guarda el contexto del usuario en Redis.
        Siempre mantiene una copia en el fallback en memoria.
        """
        # Always keep a local copy for fallback
        context["updated_at"] = datetime.utcnow().isoformat()
        self._fallback_context[phone] = context

        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:context"
            await r.setex(key, self.CONTEXT_TTL, json.dumps(context, default=str))
            logger.debug(f"Contexto guardado para {phone}")
            return True
        except Exception as e:
            logger.warning(
                f"[Memory] Redis down, context saved to fallback for {phone}: {e}"
            )
            return True  # Return True — the data is available in fallback
    
    async def update_context_field(self, phone: str, field: str, value: any) -> bool:
        """
        Actualiza un campo específico del contexto.
        """
        context = await self.get_user_context(phone)
        context[field] = value
        return await self.save_user_context(phone, context)
    
    # =========================================================================
    # MÉTODOS DE SCHEDULING (CONTEXT-AWARE)
    # =========================================================================
    
    async def save_pending_scheduling(self, phone: str, property_id: str, date_str: str = None, time_str: str = None) -> bool:
        """
        Guarda información de scheduling pendiente cuando el usuario menciona:
        - "quiero agendar para mañana a las 7pm"
        - "puedo ver el PH en centro para el viernes"
        
        El agente debe guardar esto y usarlo cuando el usuario seleccione una propiedad.
        """
        context = await self.get_user_context(phone)
        
        context["pending_scheduling_info"] = {
            "property_id": property_id,
            "date_str": date_str,
            "time_str": time_str,
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"[Memory] Pending scheduling saved for {phone}: property={property_id}, date={date_str}, time={time_str}")
        return await self.save_user_context(phone, context)
    
    async def get_pending_scheduling(self, phone: str) -> Optional[dict]:
        """
        Obtiene información de scheduling pendiente.
        Returns None si no hay información guardada.
        """
        context = await self.get_user_context(phone)
        return context.get("pending_scheduling_info")
    
    async def clear_pending_scheduling(self, phone: str) -> bool:
        """
        Limpia la información de scheduling pendiente (después de agendar exitosamente).
        """
        context = await self.get_user_context(phone)
        context["pending_scheduling_info"] = None
        return await self.save_user_context(phone, context)
    
    # =========================================================================
    # MÉTODOS DE MENSAJES (REDIS - CORTO PLAZO)
    # =========================================================================
    
    async def save_message(
        self,
        phone: str,
        role: str,
        content: str,
        media_url: Optional[str] = None
    ) -> bool:
        """
        Guarda un mensaje en la cola de mensajes del usuario (Redis).
        Mantiene los últimos MAX_MESSAGES mensajes.
        Siempre mantiene una copia en el fallback en memoria.
        """
        message = {
            "role": role,
            "content": content,
            "media_url": media_url,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Always keep a local copy for fallback
        existing = self._fallback_messages.get(phone, [])
        existing.append(message)
        if len(existing) > self.MAX_MESSAGES:
            existing = existing[-self.MAX_MESSAGES:]
        self._fallback_messages[phone] = existing

        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:messages"
            
            # Obtener mensajes actuales
            existing_json = await r.get(key)
            messages = json.loads(existing_json) if existing_json else []
            
            # Agregar nuevo mensaje
            messages.append(message)
            
            # Mantener solo los últimos MAX_MESSAGES
            if len(messages) > self.MAX_MESSAGES:
                messages = messages[-self.MAX_MESSAGES:]
            
            # Guardar con TTL
            await r.setex(key, self.MESSAGES_TTL, json.dumps(messages, default=str))
            logger.debug(f"Mensaje ({role}) guardado para {phone}")
            return True
        except Exception as e:
            logger.warning(
                f"[Memory] Redis down, message saved to fallback for {phone}: {e}"
            )
            return True  # Return True — the data is available in fallback
    
    async def get_recent_messages(self, phone: str, limit: int = 20) -> list[dict]:
        """
        Obtiene los últimos N mensajes de la conversación.
        Con fallback en memoria si Redis no está disponible.
        """
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{phone}:messages"
            data = await r.get(key)
            if data:
                messages = json.loads(data)
                # Sync fallback cache
                self._fallback_messages[phone] = messages
                return messages[-limit:] if len(messages) > limit else messages
            return []
        except Exception as e:
            logger.debug(f"[Memory] Redis unavailable, using fallback messages: {e}")
            messages = self._fallback_messages.get(phone, [])
            return messages[-limit:] if messages else []
    
    # =========================================================================
    # MÉTODOS DE PREFERENCIAS (POSTGRESQL - LARGO PLAZO)
    # =========================================================================
    
    async def update_user_preferences(
        self,
        phone: str,
        preferences: dict,
        db_session=None
    ) -> bool:
        """
        Actualiza las preferencias del usuario en PostgreSQL.
        Usa UserRepository para persistir en la tabla users.
        """
        import json
        
        try:
            from app.db.session import async_session_factory
            
            if db_session is None:
                db_session = async_session_factory()
            
            async with db_session:
                user_repo = UserRepository(User, db_session)
                user = await user_repo.get_or_create(phone)
                
                update_fields = {}
                if "name" in preferences:
                    update_fields["name"] = preferences["name"]
                if "budget_min" in preferences:
                    update_fields["budget_min"] = preferences["budget_min"]
                if "budget_max" in preferences:
                    update_fields["budget_max"] = preferences["budget_max"]
                if "location_preferences" in preferences:
                    loc_pref = preferences["location_preferences"]
                    if isinstance(loc_pref, str):
                        if loc_pref.startswith("["):
                            try:
                                loc_pref = json.loads(loc_pref)
                            except json.JSONDecodeError:
                                loc_pref = [loc_pref]
                        else:
                            loc_pref = [loc_pref]
                    update_fields["location_preferences"] = loc_pref
                if "property_type" in preferences:
                    prop_type = preferences["property_type"]
                    if isinstance(prop_type, str):
                        if prop_type.startswith("["):
                            try:
                                prop_type = json.loads(prop_type)
                            except json.JSONDecodeError:
                                prop_type = [prop_type]
                        else:
                            prop_type = [prop_type]
                    # Use SQLAlchemy ARRAY cast to match the actual column type (character varying[])
                    from sqlalchemy import cast
                    from sqlalchemy.dialects.postgresql import ARRAY
                    from sqlalchemy import String
                    update_fields["property_type"] = cast(prop_type, ARRAY(String))
                if "preferred_language" in preferences:
                    update_fields["preferred_language"] = preferences["preferred_language"]
                if "lead_score" in preferences:
                    update_fields["lead_score"] = preferences["lead_score"]
                
                update_fields["last_interaction"] = datetime.utcnow()
                
                if update_fields:
                    await user_repo.update(user.id, **update_fields)
                    await db_session.commit()
                    logger.info(f"Preferencias actualizadas para {phone}")
                
                return True
        except Exception as e:
            logger.error(f"Error al actualizar preferencias de {phone}: {e}")
            return False
    
    async def get_user_preferences(self, phone: str, db_session=None) -> Optional[dict]:
        """
        Obtiene las preferencias del usuario desde PostgreSQL.
        Con fallback silencioso si no hay BD.
        """
        try:
            from app.db.session import async_session_factory
            
            if db_session is None:
                db_session = async_session_factory()
                should_close = True
            else:
                should_close = False
            
            async with db_session:
                user_repo = UserRepository(User, db_session)
                user = await user_repo.get_by_phone(phone)
                
                if user:
                    return {
                        "name": user.name,
                        "budget_min": user.budget_min,
                        "budget_max": user.budget_max,
                        "location_preferences": user.location_preferences,
                        "property_type": user.property_type,
                        "preferred_language": user.preferred_language,
                        "lead_score": user.lead_score,
                        "last_interaction": user.last_interaction,
                    }
                return None
        except Exception as e:
            logger.warning(f"PostgreSQL no disponible, usando preferencias vacío: {e}")
            return None
    
    async def extract_and_save_preferences(
        self,
        phone: str,
        message: str,
        current_prefs: dict = None
    ) -> dict:
        """
        Extrae preferencias del mensaje del usuario y las guarda.
        
        Args:
            phone: Número de teléfono del usuario
            message: Mensaje del usuario
            current_prefs: Preferencias actuales (para no sobrescribir)
        
        Returns:
            Diccionario de preferencias extraídas
        """
        import re
        
        new_prefs = {}
        
        message_lower = message.lower()
        
        location_patterns = [
            r"(?:en|para|por)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
            r"ubicad[oa]\s+en\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
        ]
        locations = ["asunción", "encarnación", "posadas", " Oberá", "oberá", "ciudad del este", "luque", 
                   "lambaré", "san lorenzo", "villa elisa", "san antonio", "itá", "ypacaraí"]
        
        for loc in locations:
            if loc in message_lower:
                new_prefs["location_preferences"] = loc.title()
                break
        
        budget_patterns = [
            r"(?:hasta|hasta\s+)?\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:dólares?|usd|dolares)?",
            r"presupuesto\s+(?:de\s+)?\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
            r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:mil|dollars?|usd)",
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, message_lower)
            if match:
                try:
                    budget_str = match.group(1).replace(",", "")
                    budget = int(float(budget_str))
                    if "mil" in message_lower and budget < 10000:
                        budget *= 1000
                    new_prefs["budget_max"] = budget
                except:
                    pass
        
        property_types = {
            "casa": "casa",
            "casas": "casa",
            "departamento": "departamento",
            "departamentos": "departamento",
            "dpto": "departamento",
            "dptos": "departamento",
            "terreno": "terreno",
            "terrenos": "terreno",
            "oficina": "oficina",
            "oficinas": "oficina",
            "local": "local",
            "locales": "local",
            "ph": "ph",
            "duplex": "duplex",
            "campo": "campo",
        }
        
        for key, value in property_types.items():
            if key in message_lower:
                new_prefs["property_type"] = value
                break
        
        operation_types = {
            "alquilar": "alquiler",
            "alquilo": "alquiler",
            "alquiler": "alquiler",
            "renta": "alquiler",
            "rentar": "alquiler",
            "comprar": "venta",
            "compra": "venta",
            "venta": "venta",
            "vendo": "venta",
        }
        
        for key, value in operation_types.items():
            if key in message_lower:
                new_prefs["operation_type"] = value
                break
        
        bedroom_patterns = [
            r"(\d+)\s*(?:dormitorio|habitaci[ó|o]n|hab|habes|bedroom)",
            r"(?:de\s+)?(\d+)\s*(?:dormitorio|habitaci[ó|o]n|hab)",
            r"(\d+)\s*hab",
        ]
        
        for pattern in bedroom_patterns:
            match = re.search(pattern, message_lower)
            if match:
                bedrooms_val = int(match.group(1))
                # Validate: bedrooms should be 1-15, not random small values
                if 1 <= bedrooms_val <= 15:
                    new_prefs["bedrooms"] = bedrooms_val
                break
        
        bathroom_patterns = [
            r"(\d+)\s*(?:ba[ñ|n]o|baño)",
            r"(?:con\s+)?(\d+)\s*(?:ba[ñ|n]o)",
        ]
        
        for pattern in bathroom_patterns:
            match = re.search(pattern, message_lower)
            if match:
                new_prefs["bathrooms"] = int(match.group(1))
                break
        
        if current_prefs:
            # Merge new prefs without carrying over recursive context fields
            clean_prefs = {k: v for k, v in current_prefs.items() 
                          if k not in ("last_search_criteria", "conversation_stage", "selected_property_id", 
                                      "pending_scheduling_info", "last_shown_properties", "current_state",
                                      "updated_at")}
            for key, value in new_prefs.items():
                if value is not None and value != "No definido":
                    clean_prefs[key] = value
            new_prefs = clean_prefs
        
        # Ensure property_type is sent as proper array type (not JSONB)
        if "property_type" in new_prefs:
            pt = new_prefs["property_type"]
            if isinstance(pt, str):
                new_prefs["property_type"] = [pt]
        
        if new_prefs:
            await self.update_user_preferences(phone, new_prefs)
            logger.info(f"Preferencias extraídas y guardadas para {phone}: {new_prefs}")
        
        # Only save clean extraction, not the full context, to avoid recursive nesting
        last_criteria = {
            "search_text": message[:200],
            "extracted_prefs": {k: v for k, v in new_prefs.items() 
                               if k in ("property_type", "bedrooms", "bathrooms", "budget_min", "budget_max",
                                        "location_preferences", "operation_type")},
        }
        await self.update_context_field(phone, "last_search_criteria", last_criteria)
        
        return new_prefs
    
    async def get_merged_context(self, phone: str) -> dict:
        """
        Obtiene contexto combinado (Redis + PostgreSQL) para el LLM.
        Con fallback silencioso si no hay BD.
        
        Returns:
            Diccionario con preferencias combinadas de ambas fuentes
        """
        try:
            redis_context = await self.get_user_context(phone)
        except Exception as e:
            logger.warning(f"Error get_user_context, usando default: {e}")
            redis_context = {"current_state": "idle", "conversation_stage": "new"}
        
        try:
            postgres_prefs = await self.get_user_preferences(phone)
        except Exception as e:
            logger.warning(f"Error get_user_preferences, usando vacío: {e}")
            postgres_prefs = None
        
        merged = {}
        
        for key in ["location_preferences", "property_type", "budget_min", "budget_max", 
                   "operation_type", "bedrooms", "bathrooms", "name"]:
            if postgres_prefs and postgres_prefs.get(key):
                merged[key] = postgres_prefs[key]
            elif redis_context.get(key):
                merged[key] = redis_context[key]
        
        merged["last_search_criteria"] = redis_context.get("last_search_criteria")
        
        merged["conversation_stage"] = redis_context.get("conversation_stage", "new")
        
        return merged
    
    # =========================================================================
    # MÉTODOS DE RESUMEN (LLM - FUTURO)
    # =========================================================================
    
    async def get_conversation_summary(self, phone: str) -> str:
        """
        Obtiene el resumen de conversación previo.
        Este método será implementado con MiniMax para resumir conversaciones.
        
        Por ahora retorna un resumen básico desde Redis.
        """
        try:
            r = await self._get_redis_with_retry()
        except Exception as e:
            logger.debug(f"[Memory] Redis no disponible para summary: {e}")
            return ""
        key = f"user:{phone}:summary"
        
        try:
            summary = await r.get(key)
            return summary if summary else ""
        except Exception as e:
            logger.error(f"Error al obtener summary de {phone}: {e}")
            return ""
    
    async def save_conversation_summary(self, phone: str, summary: str) -> bool:
        """
        Guarda el resumen de conversación (generado por LLM).
        """
        try:
            r = await self._get_redis_with_retry()
        except Exception as e:
            logger.debug(f"[Memory] Redis no disponible para save summary: {e}")
            return False
        key = f"user:{phone}:summary"
        
        try:
            await r.setex(key, self.MESSAGES_TTL, summary)
            return True
        except Exception as e:
            logger.warning(f"Error al guardar summary de {phone}: {e}")
            return False
    
    async def summarize_conversation(self, phone: str) -> str:
        """
        Resume la conversación actual usando MiniMax.
        
        PLACEHOLDER: Por ahora solo retorna los últimos mensajes.
        MiniMax será integrado posteriormente para generar resúmenes.
        """
        messages = await self.get_recent_messages(phone)
        
        if not messages:
            return ""
        
        # Por ahora, simplemente retornamos los últimos 5 mensajes como "resumen"
        recent = messages[-5:]
        summary = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in recent])
        
        # TODO: Integrar con MiniMax para generar resumen inteligente
        # prompt = f"Resume esta conversación en español:\n{summary}"
        # summary = await llm_client.chat(prompt)
        
        await self.save_conversation_summary(phone, summary)
        return summary
    
    # =========================================================================
    # LIMPIEZA
    # =========================================================================
    
    async def clear_short_term_memory(self, phone: str) -> bool:
        """
        Limpia la memoria de corto plazo (Redis + fallback en memoria).
        Mantiene las preferencias en PostgreSQL.
        """
        # Always clear fallback first
        self._fallback_context.pop(phone, None)
        self._fallback_messages.pop(phone, None)

        try:
            r = await self._get_redis_with_retry()
        except Exception as e:
            logger.debug(f"[Memory] Redis no disponible para clear, fallback cleared: {e}")
            return True
        
        try:
            keys = [
                f"user:{phone}:context",
                f"user:{phone}:messages",
                f"user:{phone}:summary",
            ]
            
            for key in keys:
                await r.delete(key)
            
            logger.info(f"Memoria de corto plazo limpiada para {phone}")
            return True
        except Exception as e:
            logger.error(f"Error al limpiar memoria de {phone}: {e}")
            return False
    
    async def reset_user_context(self, phone: str) -> bool:
        """
        Delete all Redis keys for a user + clear fallback caches.
        More aggressive than clear_short_term_memory — also resets
        the PostgreSQL user preferences to defaults so the next
        conversation starts fresh.

        Returns True on success (even if PostgreSQL cleanup fails).
        """
        # 1. Always clear in-memory fallback first
        self._fallback_context.pop(phone, None)
        self._fallback_messages.pop(phone, None)

        # 2. Clear Redis keys
        try:
            r = await self._get_redis_with_retry()
            keys = [
                f"user:{phone}:context",
                f"user:{phone}:messages",
                f"user:{phone}:summary",
            ]
            for key in keys:
                await r.delete(key)
            logger.info(f"[Memory] Redis context reset for {phone}")
        except Exception as e:
            logger.debug(f"[Memory] Redis unavailable for reset, fallback cleared: {e}")

        # 3. Reset PostgreSQL user preferences
        try:
            from app.db.session import async_session_factory
            async with async_session_factory() as session:
                from app.db.repository import UserRepository
                from app.db.models import User
                repo = UserRepository(User, session)
                user = await repo.get_by_phone(phone)
                if user:
                    user.location_preferences = None
                    user.property_type = None
                    user.budget_min = None
                    user.budget_max = None
                    user.last_interaction = None
                    user.lead_score = 0
                    await session.commit()
                    logger.info(f"[Memory] PostgreSQL preferences reset for {phone}")
                else:
                    logger.info(f"[Memory] No user record found for {phone}, nothing to reset in DB")
        except Exception as e:
            logger.warning(f"[Memory] PostgreSQL reset failed for {phone}: {e}")

        logger.info(f"[Memory] Contexto completamente reseteado para {phone}")
        return True

    async def clear_user(self, phone: str) -> bool:
        """
        Limpia toda la memoria del usuario (Redis + PostgreSQL).
        Alias para compatibilidad con frontend.
        """
        try:
            await self.clear_short_term_memory(phone)
            logger.info(f"Usuario {phone} limpiado completamente")
            return True
        except Exception as e:
            logger.error(f"Error al limpiar usuario {phone}: {e}")
            return False
    
    async def close(self):
        """Cierra conexión Redis."""
        if self._redis:
            await self._redis.close()

    # =========================================================================
    # DEAD-LETTER QUEUE (message retry)
    # =========================================================================

    async def save_dead_letter(
        self,
        messages: list,
        error: str,
        ttl: int = 604800,  # 7 days
    ) -> bool:
        """Save message payloads to a dead-letter queue for later retry.

        Uses a Redis list: ``dead_letter:messages``.  Each entry is a JSON
        blob with the original messages, a timestamp, and the error string.
        Oldest entries are trimmed to 10 000 to avoid unbounded growth.

        Returns True on success, False if Redis is unavailable.
        """
        try:
            r = await self._get_redis_with_retry()
        except Exception:
            logger.error("[DeadLetter] Redis unavailable — cannot save dead-letter")
            return False

        key = "dead_letter:messages"
        entry = {
            "messages": messages,
            "crashed_at": datetime.utcnow().isoformat(),
            "error": error[:500],
        }
        try:
            await r.lpush(key, json.dumps(entry, default=str))
            await r.ltrim(key, 0, 9999)
            await r.expire(key, ttl)
            logger.info(
                "[DeadLetter] Saved {} message(s) to dead-letter queue (error: {})",
                len(messages),
                error[:80],
            )
            return True
        except Exception as e:
            logger.error("[DeadLetter] Failed to save dead-letter entry: {}", e)
            return False

    async def get_dead_letter_count(self) -> int:
        """Return the number of entries in the dead-letter queue."""
        try:
            r = await self._get_redis_with_retry()
        except Exception:
            return 0
        try:
            return await r.llen("dead_letter:messages")
        except Exception:
            return 0


# Instancia global del gestor de memoria
memory_manager = MemoryManager()