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
from app.core.identity import get_identity_key
from app.db.models import User
from app.db.repository import UserRepository


class MemoryManager:
    """
    Gestor de memoria híbrida para el bot.
    Combina Redis (corto plazo) + PostgreSQL (largo plazo).
    Usa Async Connection Pool para mejor rendimiento.
    """
    
    CONTEXT_TTL = get_settings().CONTEXT_TTL if hasattr(get_settings(), 'CONTEXT_TTL') else 86400
    MESSAGES_TTL = get_settings().CONTEXT_TTL if hasattr(get_settings(), 'CONTEXT_TTL') else 86400
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
        identity_key = get_identity_key() or phone
        _DEFAULT = {
            "current_state": "idle",
            "last_search_criteria": None,
            "selected_property_id": None,
            "conversation_stage": "new",
            "pending_scheduling_info": None,
        }

        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:context"
            data = await r.get(key)
            if data:
                context = json.loads(data)
                # Sync fallback cache so it's always up to date
                self._fallback_context[identity_key] = context
                return context
            return _DEFAULT
        except Exception as e:
            logger.debug(f"[Memory] Redis unavailable, using fallback context: {e}")
            return self._fallback_context.get(identity_key, _DEFAULT)
    
    async def save_user_context(self, phone: str, context: dict) -> bool:
        """
        Guarda el contexto del usuario en Redis.
        Siempre mantiene una copia en el fallback en memoria.
        """
        identity_key = get_identity_key() or phone
        # Always keep a local copy for fallback
        context["updated_at"] = datetime.utcnow().isoformat()
        self._fallback_context[identity_key] = context

        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:context"
            await r.setex(key, self.CONTEXT_TTL, json.dumps(context, default=str))
            logger.debug(f"Contexto guardado para {identity_key}")
            return True
        except Exception as e:
            logger.warning(
                f"[Memory] Redis down, context saved to fallback for {identity_key}: {e}"
            )
            return True  # Return True — the data is available in fallback
    
    async def update_context_field(self, phone: str, field: str, value: any) -> bool:
        """
        Actualiza un campo específico del contexto.
        """
        identity_key = get_identity_key() or phone
        context = await self.get_user_context(identity_key)
        context[field] = value
        return await self.save_user_context(identity_key, context)
    
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
        identity_key = get_identity_key() or phone
        context = await self.get_user_context(identity_key)
        
        context["pending_scheduling_info"] = {
            "active": True,
            "property_id": property_id,
            "date_str": date_str,
            "time_str": time_str,
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"[Memory] Pending scheduling saved for {identity_key}: property={property_id}, date={date_str}, time={time_str}")
        return await self.save_user_context(identity_key, context)
    
    async def get_pending_scheduling(self, phone: str) -> Optional[dict]:
        """
        Obtiene información de scheduling pendiente.
        Returns None si no hay información guardada.
        """
        identity_key = get_identity_key() or phone
        context = await self.get_user_context(identity_key)
        return context.get("pending_scheduling_info")
    
    async def clear_pending_scheduling(self, phone: str) -> bool:
        """
        Limpia la información de scheduling pendiente (después de agendar exitosamente).
        """
        identity_key = get_identity_key() or phone
        context = await self.get_user_context(identity_key)
        context["pending_scheduling_info"] = None
        return await self.save_user_context(identity_key, context)

    async def is_duplicate_message(self, message_id: str, ttl: int = 300) -> bool:
        """
        Returns True if message_id was already processed (duplicate).

        Uses Redis SET NX EX for an atomic check-and-mark in a single round-trip.
        Because the key lives in Redis (not in-process memory) it survives server
        restarts, so a Render redeploy mid-processing can no longer cause a message
        to be delivered twice.

        Falls back to False (allow through) on any Redis error — the in-process
        _is_duplicate() in webhook.py still guards within the same process lifetime.
        """
        key = f"dedup:msg:{message_id}"
        try:
            r = await self._get_redis_with_retry()
            # SET key 1 NX EX ttl → returns True if key was set (first time seen)
            #                      → returns None  if key already existed (duplicate)
            result = await r.set(key, "1", nx=True, ex=ttl)
            is_dup = result is None
            if is_dup:
                logger.info(f"[Memory] Redis dedup: duplicate message_id={message_id}")
            return is_dup
        except Exception as e:
            logger.warning(f"[Memory] Redis dedup unavailable, allowing message through: {e}")
            return False  # Fail open — in-process dict is still the last line of defence

    # =========================================================================
    # MÉTODOS DE RESET (LIMPIEZA DE DATOS)
    # =========================================================================

    async def reset_all_users(self) -> int:
        """
        Resetea el contexto de TODOS los usuarios.
        Barre todas las claves Redis con patrón user:* y las elimina.
        También resetea la tabla users en PostgreSQL.

        Returns:
            Cantidad de keys eliminadas de Redis
        """
        logger.info("[Memory] Resetting ALL users context")
        total_deleted = 0

        # 1. Clear in-memory fallbacks entirely
        self._fallback_context.clear()
        self._fallback_messages.clear()
        logger.info("[Memory] In-memory fallbacks cleared")

        # 2. Clear ALL Redis user keys
        try:
            r = await self._get_redis_with_retry()
            cursor = 0
            pattern = "user:*"
            deleted_batch = 0
            while True:
                cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await r.delete(*keys)
                    deleted_batch += len(keys)
                if cursor == 0:
                    break
            total_deleted += deleted_batch
            logger.info(f"[Memory] Redis: deleted {deleted_batch} user key(s)")

            # Also clear dedup keys
            dedup_cursor = 0
            dedup_deleted = 0
            while True:
                dedup_cursor, dedup_keys = await r.scan(cursor=dedup_cursor, match="dedup:*", count=100)
                if dedup_keys:
                    await r.delete(*dedup_keys)
                    dedup_deleted += len(dedup_keys)
                if dedup_cursor == 0:
                    break
            total_deleted += dedup_deleted
            if dedup_deleted:
                logger.info(f"[Memory] Redis: deleted {dedup_deleted} dedup key(s)")
        except Exception as e:
            logger.warning(f"[Memory] Redis flush failed: {e}")

        # 3. Clear PostgreSQL user preferences (reset to defaults)
        try:
            from app.db.session import async_session_factory
            from sqlalchemy import update
            from app.db.models import User
            async with async_session_factory() as session:
                stmt = (
                    update(User)
                    .values(
                        name=None,
                        budget_min=None,
                        budget_max=None,
                        location_preferences=None,
                        property_type=None,
                        lead_score=0,
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                logger.info(f"[Memory] PostgreSQL: reset {result.rowcount} user(s)")
        except Exception as e:
            logger.warning(f"[Memory] PostgreSQL reset failed: {e}")

        return total_deleted

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
        identity_key = get_identity_key() or phone
        message = {
            "role": role,
            "content": content,
            "media_url": media_url,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Always keep a local copy for fallback
        existing = self._fallback_messages.get(identity_key, [])
        existing.append(message)
        if len(existing) > self.MAX_MESSAGES:
            existing = existing[-self.MAX_MESSAGES:]
        self._fallback_messages[identity_key] = existing

        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:messages"
            
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
            logger.debug(f"Mensaje ({role}) guardado para {identity_key}")
            return True
        except Exception as e:
            logger.warning(
                f"[Memory] Redis down, message saved to fallback for {identity_key}: {e}"
            )
            return True  # Return True — the data is available in fallback
    
    async def get_recent_messages(self, phone: str, limit: int = 20) -> list[dict]:
        """
        Obtiene los últimos N mensajes de la conversación.
        Con fallback en memoria si Redis no está disponible.
        """
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:messages"
            data = await r.get(key)
            if data:
                messages = json.loads(data)
                # Sync fallback cache
                self._fallback_messages[identity_key] = messages
                return messages[-limit:] if len(messages) > limit else messages
            return []
        except Exception as e:
            logger.debug(f"[Memory] Redis unavailable, using fallback messages: {e}")
            messages = self._fallback_messages.get(identity_key, [])
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
        identity_key = get_identity_key() or phone
        import json
        
        try:
            from app.db.session import async_session_factory
            
            if db_session is None:
                db_session = async_session_factory()
            
            async with db_session:
                user_repo = UserRepository(User, db_session)
                user = await user_repo.get_or_create(identity_key)
                
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
                    logger.info(f"Preferencias actualizadas para {identity_key}")
                
                return True
        except Exception as e:
            logger.error(f"Error al actualizar preferencias de {identity_key}: {e}")
            return False
    
    async def get_user_preferences(self, phone: str, db_session=None) -> Optional[dict]:
        """
        Obtiene las preferencias del usuario desde PostgreSQL.
        Con fallback silencioso si no hay BD.
        """
        identity_key = get_identity_key() or phone
        try:
            from app.db.session import async_session_factory
            
            if db_session is None:
                db_session = async_session_factory()
                should_close = True
            else:
                should_close = False
            
            async with db_session:
                user_repo = UserRepository(User, db_session)
                user = None
                # Try BSUID first if identity_key differs from phone
                if identity_key != phone:
                    user = await user_repo.get_by_bsuid(identity_key)
                if not user:
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
        identity_key = get_identity_key() or phone
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
            r"(?:hasta|hasta\s+)\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:dólares?|usd|dolares)?",
            r"presupuesto\s+(?:de\s+)?\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
            r"(?:de\s+)?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:mil|dollars?|usd)",
            r"\b(\d{4,6})\s*(?:dólares?|usd|dolares|pesos?|ars)\b",
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
            await self.update_user_preferences(identity_key, new_prefs)
            logger.info(f"Preferencias extraídas y guardadas para {identity_key}: {new_prefs}")
        
        # Only save clean extraction, not the full context, to avoid recursive nesting
        last_criteria = {
            "search_text": message[:200],
            "extracted_prefs": {k: v for k, v in new_prefs.items() 
                               if k in ("property_type", "bedrooms", "bathrooms", "budget_min", "budget_max",
                                        "location_preferences", "operation_type")},
        }
        await self.update_context_field(identity_key, "last_search_criteria", last_criteria)
        
        return new_prefs
    
    async def get_merged_context(self, phone: str) -> dict:
        """
        Obtiene contexto combinado (Redis + PostgreSQL) para el LLM.
        Con fallback silencioso si no hay BD.
        
        Returns:
            Diccionario con preferencias combinadas de ambas fuentes
        """
        identity_key = get_identity_key() or phone
        try:
            redis_context = await self.get_user_context(identity_key)
        except Exception as e:
            logger.warning(f"Error get_user_context, usando default: {e}")
            redis_context = {"current_state": "idle", "conversation_stage": "new"}
        
        try:
            postgres_prefs = await self.get_user_preferences(identity_key)
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

        # Context fields needed by the agent's auto-resolve and nudges
        merged["last_shown_properties"] = redis_context.get("last_shown_properties")
        merged["selected_property_id"] = redis_context.get("selected_property_id")
        merged["pending_scheduling_info"] = redis_context.get("pending_scheduling_info")

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
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
        except Exception as e:
            logger.debug(f"[Memory] Redis no disponible para summary: {e}")
            return ""
        key = f"user:{identity_key}:summary"
        
        try:
            summary = await r.get(key)
            return summary if summary else ""
        except Exception as e:
            logger.error(f"Error al obtener summary de {identity_key}: {e}")
            return ""
    
    async def save_conversation_summary(self, phone: str, summary: str) -> bool:
        """
        Guarda el resumen de conversación (generado por LLM).
        """
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
        except Exception as e:
            logger.debug(f"[Memory] Redis no disponible para save summary: {e}")
            return False
        key = f"user:{identity_key}:summary"
        
        try:
            await r.setex(key, self.MESSAGES_TTL, summary)
            return True
        except Exception as e:
            logger.warning(f"Error al guardar summary de {identity_key}: {e}")
            return False
    
    async def summarize_conversation(self, phone: str) -> str:
        """
        v2.0: Resume la conversación usando el LLM para generar un resumen compacto.

        Solo resume mensajes 6+ (los primeros 5 se mantienen completos).
        El resumen se cachea en Redis con TTL de 24h.
        """
        identity_key = get_identity_key() or phone
        messages = await self.get_recent_messages(identity_key, limit=50)

        if not messages or len(messages) <= 10:
            return ""  # Not enough messages to justify summarization

        # Summary threshold: only summarize if there are >10 messages total
        # Keep last 5 full, summarize the rest
        to_summarize = messages[:-5] if len(messages) > 5 else []
        if not to_summarize:
            return ""

        # Build a compact representation for the LLM
        conv_text = "\n".join([
            f"{m['role']}: {m['content'][:200]}" for m in to_summarize
        ])

        try:
            from app.agents.llm_router import llm_router

            summary_prompt = (
                "Resume esta conversacion de WhatsApp con un asistente inmobiliario "
                "en Argentina. Incluye SOLO datos utiles para continuar la conversacion: "
                "que busca el usuario (tipo de propiedad, zona, presupuesto, operacion), "
                "que propiedades vio (IDs), si agendo visita, si pidio fotos, "
                "y cualquier preferencia o restriccion mencionada. "
                "Se conciso, maximo 4 lineas. No incluyas saludos ni cortesias.\n\n"
                f"Conversacion:\n{conv_text}\n\nResumen:"
            )

            response = await llm_router.chat(
                message=summary_prompt,
                system_prompt="Eres un asistente que resume conversaciones.",
                max_completion_tokens=200,
            )

            if response and len(response.strip()) > 10:
                summary = f"[Resumen de conversacion anterior]\n{response.strip()}"
                await self.save_conversation_summary(identity_key, summary)
                logger.info(f"[Memory] Generated LLM summary for {str(identity_key)[-4:]} ({len(response)} chars)")
                return summary

        except Exception as e:
            logger.warning(f"[Memory] LLM summarization failed, using fallback: {e}")

        # Fallback: simple concatenation
        recent = to_summarize[-5:]
        summary = "[Resumen]\n" + "\n".join([
            f"{m['role']}: {m['content'][:100]}" for m in recent
        ])
        await self.save_conversation_summary(identity_key, summary)
        return summary

    # ── v2.0 Sliding window: recent messages + summary ──────────────────

    async def get_messages_with_summary(self, phone: str) -> list[dict]:
        """
        v2.0: Returns last 5 full messages + a summary of older messages.

        This keeps the context window stable regardless of conversation length.
        Returns a list of message dicts ready for the LLM.
        """
        identity_key = get_identity_key() or phone
        messages = await self.get_recent_messages(identity_key, limit=50)

        if len(messages) <= 10:
            return messages  # Short conversation, return all

        # Get cached summary, or generate one
        summary = await self.get_conversation_summary(identity_key)
        if not summary or len(summary) < 20:
            summary = await self.summarize_conversation(identity_key)

        # Return: summary as system message + last 5 full messages
        result = []
        if summary:
            result.append({
                "role": "system",
                "content": summary,
            })

        result.extend(messages[-5:])
        return result
    
    # =========================================================================
    # LIMPIEZA
    # =========================================================================
    
    async def clear_short_term_memory(self, phone: str) -> bool:
        """
        Limpia la memoria de corto plazo (Redis + fallback en memoria).
        Mantiene las preferencias en PostgreSQL.
        """
        identity_key = get_identity_key() or phone
        # Always clear fallback first
        self._fallback_context.pop(identity_key, None)
        self._fallback_messages.pop(identity_key, None)

        try:
            r = await self._get_redis_with_retry()
        except Exception as e:
            logger.debug(f"[Memory] Redis no disponible para clear, fallback cleared: {e}")
            return True
        
        try:
            keys = [
                f"user:{identity_key}:context",
                f"user:{identity_key}:messages",
                f"user:{identity_key}:summary",
            ]
            
            for key in keys:
                await r.delete(key)
            
            logger.info(f"Memoria de corto plazo limpiada para {identity_key}")
            return True
        except Exception as e:
            logger.error(f"Error al limpiar memoria de {identity_key}: {e}")
            return False
    
    async def reset_user_context(self, phone: str) -> bool:
        """
        Delete all Redis keys for a user + clear fallback caches.
        Resets the PostgreSQL user record (name, preferences) AND
        deletes all appointments linked to this user so the next
        conversation starts completely fresh.

        Returns True on success (even if PostgreSQL cleanup fails).
        """
        identity_key = get_identity_key() or phone
        # 1. Always clear in-memory fallback first
        self._fallback_context.pop(identity_key, None)
        self._fallback_messages.pop(identity_key, None)

        # 2. Clear Redis keys
        try:
            r = await self._get_redis_with_retry()
            keys = [
                f"user:{identity_key}:context",
                f"user:{identity_key}:messages",
                f"user:{identity_key}:summary",
                f"user:{identity_key}:state",
                f"user:{identity_key}:previous_state",
                f"user:{identity_key}:state_context",
            ]
            for key in keys:
                await r.delete(key)
            logger.info(f"[Memory] Redis context reset for {identity_key}")
        except Exception as e:
            logger.debug(f"[Memory] Redis unavailable for reset, fallback cleared: {e}")

        # 3. Reset PostgreSQL: clear name, preferences, and delete appointments
        try:
            from app.db.session import async_session_factory
            from app.db.repository import UserRepository
            from app.db.models import User
            from sqlalchemy import text as _text, delete as _delete

            async with async_session_factory() as session:
                user_repo = UserRepository(User, session)
                user = None
                # Try BSUID first if identity_key differs from phone
                if identity_key != phone:
                    user = await user_repo.get_by_bsuid(identity_key)
                if not user:
                    user = await user_repo.get_by_phone(phone)
                if user:
                    user_id = user.id

                    # Use raw SQL for the user update to avoid JSONB/text[] type cast conflict.
                    # ORM attribute assignment triggers autoflush with ::jsonb cast which fails
                    # when the DB column is actually text[].
                    await session.execute(
                        _text(
                            "UPDATE users SET name=NULL, location_preferences=NULL, "
                            "property_type=NULL, budget_min=NULL, budget_max=NULL, "
                            "lead_score=0, last_interaction=NULL, extra_data=NULL, email=NULL "
                            "WHERE id=:uid"
                        ),
                        {"uid": user_id},
                    )
                    logger.info(f"[Memory] User preferences cleared (raw SQL) for {identity_key}")

                    # Delete appointments via raw SQL (no autoflush risk)
                    from app.db.models import Appointment
                    apt_result = await session.execute(
                        _text("DELETE FROM appointments WHERE user_id=:uid RETURNING id"),
                        {"uid": user_id},
                    )
                    apt_count = apt_result.rowcount
                    if apt_count:
                        logger.info(f"[Memory] Deleted {apt_count} appointments for {identity_key}")

                    # Delete conversations via raw SQL
                    conv_result = await session.execute(
                        _text("DELETE FROM conversations WHERE user_id=:uid RETURNING id"),
                        {"uid": user_id},
                    )
                    conv_count = conv_result.rowcount
                    if conv_count:
                        logger.info(f"[Memory] Deleted {conv_count} conversations for {identity_key}")

                    await session.commit()
                    logger.info(f"[Memory] PostgreSQL full reset for {identity_key}")
                else:
                    logger.info(f"[Memory] No user record found for {identity_key}, nothing to reset in DB")
        except Exception as e:
            logger.warning(f"[Memory] PostgreSQL reset failed for {identity_key}: {e}")

        logger.info(f"[Memory] Contexto completamente reseteado para {identity_key}")
        return True

    async def clear_user(self, phone: str) -> bool:
        """
        Limpia toda la memoria del usuario (Redis + PostgreSQL).
        Alias para compatibilidad con frontend.
        """
        identity_key = get_identity_key() or phone
        try:
            await self.clear_short_term_memory(identity_key)
            logger.info(f"Usuario {identity_key} limpiado completamente")
            return True
        except Exception as e:
            logger.error(f"Error al limpiar usuario {identity_key}: {e}")
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

    async def get_user_name(self, phone: str) -> Optional[str]:
        """Get user's full name from Redis or DB."""
        identity_key = get_identity_key() or phone
        ctx = await self.get_user_context(identity_key)
        if ctx and ctx.get("name"):
            return ctx["name"]
        try:
            from app.db.repository import UserRepository
            from app.db.models import User
            from app.db.session import async_session_factory

            async with async_session_factory() as session:
                repo = UserRepository(User, session)
                user = None
                # Try BSUID first if identity_key differs from phone
                if identity_key != phone:
                    user = await repo.get_by_bsuid(identity_key)
                if not user:
                    user = await repo.get_by_phone(phone)
                return user.name if user and user.name else None
        except Exception:
            return None

    async def save_user_name(self, phone: str, name: str) -> None:
        """Save user's full name to both Redis and DB."""
        identity_key = get_identity_key() or phone
        await self.update_context_field(identity_key, "name", name)
        try:
            from app.db.repository import UserRepository
            from app.db.models import User
            from app.db.session import async_session_factory

            async with async_session_factory() as session:
                repo = UserRepository(User, session)
                user = None
                # Try BSUID first if identity_key differs from phone
                if identity_key != phone:
                    user = await repo.get_by_bsuid(identity_key)
                if not user:
                    user = await repo.get_by_phone(phone)
                if user:
                    await repo.update(user.id, name=name)
                    await session.commit()
        except Exception as e:
            logger.warning("save_user_name: DB error - %s", e)

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