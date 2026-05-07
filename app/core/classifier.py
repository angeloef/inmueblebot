"""
Clasificador de intents usando MiniMax M2.5.
Utiliza structured output con Pydantic para resultados deterministicos.
"""
import asyncio
import json
import hashlib
from typing import Optional
from datetime import datetime
import redis.asyncio as redis
from loguru import logger
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.intent import Intent, INTENT_DESCRIPTIONS


# ============================================================================
# Esquemas Pydantic para clasificación
# ============================================================================


class ExtractedEntities(BaseModel):
    """Entidades extraídas del mensaje del usuario."""
    budget_min: Optional[int] = Field(None, description="Presupuesto mínimo en USD")
    budget_max: Optional[int] = Field(None, description="Presupuesto máximo en USD")
    location: Optional[str] = Field(None, description="Ubicación o ciudad buscada")
    property_type: Optional[str] = Field(None, description="Tipo de propiedad: casa, departamento, terreno, etc.")
    bedrooms: Optional[int] = Field(None, description="Número de dormitorios")
    bathrooms: Optional[int] = Field(None, description="Número de baños")
    area_min: Optional[int] = Field(None, description="Área mínima en m2")
    operation_type: Optional[str] = Field(None, description="Tipo de operación: venta o alquiler")


class IntentClassification(BaseModel):
    """Resultado de la clasificación de intent."""
    intent: Intent = Field(..., description="El intent clasificado")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Nivel de confianza de la clasificación (0-1)")
    extracted_entities: ExtractedEntities = Field(default_factory=ExtractedEntities, description="Entidades extraídas del mensaje")
    reasoning: Optional[str] = Field(None, description="Razón de la clasificación")


# ============================================================================
# Few-shot examples (Spanish and English)
# ============================================================================


FEW_SHOT_EXAMPLES = """
Ejemplos de clasificación:

1. "Hola, buenos días" → GREETING
2. "Hola, quiero comprar una casa en Asunción" → PROPERTY_SEARCH (ubicación=Asunción, operation_type=venta)
3. "Busco departamento para alquiler en Encarnación hasta 500 USD" → PROPERTY_SEARCH (location=Encarnación, budget_max=500, property_type=departamento, operation_type=alquiler)
4. "Tengo presupuesto 200000 USD, busco casa de 3 habitaciones en Posadas" → PROPERTY_SEARCH (budget_max=200000, location=Posadas, bedrooms=3, property_type=casa, operation_type=venta)
5. "Quiero saber más detalles de la casa en Villa Edna" → PROPERTY_DETAILS
6. "Cuántos metros tiene el terreno?" → PROPERTY_DETAILS
7. "Quiero agendar una visita a la propiedad" → SCHEDULE_APPOINTMENT
8. "Puedo ir a ver la casa mañana a las 10?" → SCHEDULE_APPOINTMENT
9. "Cómo funciona el proceso de compra?" → FAQ
10. "Cobran comisión por la gestión?" → FAQ
11. "Necesito hablar con un agente humano" → HUMAN_HANDOFF
12. "Hay alguien que me pueda atender personalmente?" → HUMAN_HANDOFF
13. "Xyz123" → UNKNOWN
"""


# ============================================================================
# Prompt para clasificación
# ============================================================================


CLASSIFICATION_PROMPT = """Eres un asistente de clasificación de mensajes para un chatbot de bienes raíces.

Tu tarea es clasificar el mensaje del usuario en una de las siguientes categorías:
{intent_list}

{examples}

 mensaje del usuario: "{message}"

Clasifica el mensaje y extrae las entidades relevantes. Responde en formato JSON con esta estructura:
{{
    "intent": "NOMBRE_DEL_INTENT",
    "confidence": 0.0-1.0,
    "extracted_entities": {{
        "budget_min": número o null,
        "budget_max": número o null,
        "location": "texto o null",
        "property_type": "casa/departamento/terreno/oficina/local o null",
        "bedrooms": número o null,
        "bathrooms": número o null,
        "area_min": número o null,
        "operation_type": "venta/alquiler o null"
    }},
    "reasoning": "breve explicación de por qué se clasificó así"
}}

Usa temperature=0 para resultados deterministas.
Si no puedes clasificar con confianza > 0.7, usa UNKNOWN."""


# ============================================================================
# Clasificador de intents
# ============================================================================


class IntentClassifier:
    """
    Clasificador de intents usando MiniMax M2.5.
    Utiliza Redis para cachear resultados.
    """
    
    CACHE_TTL = 300  # 5 minutos
    MAX_RETRIES = 3
    
    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._redis_url = settings.resolve_redis_url()
        self._api_key = settings.OPENROUTER_API_KEY
        self._model = settings.OPENROUTER_MODEL
    
    async def _get_redis_with_retry(self) -> redis.Redis:
        """Obtiene cliente Redis con reintentos."""
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                if self._redis is None:
                    self._redis = redis.from_url(
                        self._redis_url,
                        decode_responses=True,
                        socket_connect_timeout=3,
                        socket_timeout=3
                    )
                
                await self._redis.ping()
                return self._redis
                
            except Exception as e:
                last_error = e
                delay = 0.5 * (2 ** attempt)
                logger.warning(f"[Classifier] Intento {attempt + 1}/{self.MAX_RETRIES}: {e}")
                await asyncio.sleep(delay)
        
        logger.error(f"[Classifier] Redis no disponible después de {self.MAX_RETRIES} intentos")
        raise last_error
    
    async def _get_redis(self) -> redis.Redis:
        """Obtiene cliente Redis usando retry."""
        try:
            return await self._get_redis_with_retry()
        except Exception:
            # Return a dummy redis-like object that will fail gracefully
            return None
    
    def _get_cache_key(self, message: str) -> str:
        """Genera clave de cache basada en hash del mensaje."""
        msg_hash = hashlib.md5(message.encode()).hexdigest()
        return f"intent:cache:{msg_hash}"
    
    async def classify(self, message: str) -> IntentClassification:
        """
        Clasifica el mensaje del usuario.
        
        Args:
            message: Mensaje del usuario a clasificar
            
        Returns:
            IntentClassification con el intent, confianza y entidades
        """
        # Verificar cache
        try:
            r = await self._get_redis_with_retry()
            cache_key = self._get_cache_key(message)
            
            cached = await r.get(cache_key)
            if cached:
                logger.debug(f"Intent cache hit: {message[:50]}...")
                return IntentClassification.model_validate_json(cached)
        except Exception as e:
            logger.debug(f"Redis cache no disponible: {e}")
        
        # Construir prompt
        intent_list = "\n".join([f"- {i.value}: {INTENT_DESCRIPTIONS[i]}" for i in Intent])
        prompt = CLASSIFICATION_PROMPT.format(
            intent_list=intent_list,
            examples=FEW_SHOT_EXAMPLES,
            message=message
        )
        
        # Llamar al LLM
        try:
            result = await self._call_llm(prompt)
            
            # Parsear respuesta
            classification = self._parse_response(result)
            
            # Guardar en cache
            try:
                await r.setex(cache_key, self.CACHE_TTL, classification.model_dump_json())
            except Exception as e:
                logger.warning(f"Error al guardar cache: {e}")
            
            logger.info(f"Intent clasificado: {classification.intent.value} (confianza: {classification.confidence})")
            return classification
            
        except Exception as e:
            logger.error(f"Error al clasificar intent: {e}")
            # Fallback a UNKNOWN
            return IntentClassification(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                extracted_entities=ExtractedEntities(),
                reasoning="Error en el clasificador"
            )
    
    async def _call_llm(self, prompt: str) -> str:
        """
        Llama a MiniMax via OpenRouter para clasificación.
        """
        import httpx
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://inmueblebot.com",
            "X-Title": "InmuebleBot"
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 500
        }
        
        # Hard limit: classification must not block the webhook for more than 5 s
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            # Check for errors in response
            if response.status_code != 200:
                error_data = response.json()
                raise Exception(f"API error: {error_data.get('error', {}).get('message', 'Unknown error')}")

            data = response.json()

            if "choices" not in data or len(data["choices"]) == 0:
                raise Exception("No choices in response")

            return data["choices"][0]["message"]["content"]
    
    def _parse_response(self, response: str) -> IntentClassification:
        """Parsea la respuesta del LLM al formato esperado."""
        try:
            # Intentar extraer JSON de la respuesta
            # El LLM puede devolver texto adicional
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                # Mapear intent string a enum
                intent_str = data.get("intent", "unknown").upper()
                try:
                    intent = Intent(intent_str)
                except ValueError:
                    intent = Intent.UNKNOWN
                
                # Extraer entidades
                entities = data.get("extracted_entities", {})
                
                return IntentClassification(
                    intent=intent,
                    confidence=float(data.get("confidence", 0.5)),
                    extracted_entities=ExtractedEntities(
                        budget_min=entities.get("budget_min"),
                        budget_max=entities.get("budget_max"),
                        location=entities.get("location"),
                        property_type=entities.get("property_type"),
                        bedrooms=entities.get("bedrooms"),
                        bathrooms=entities.get("bathrooms"),
                        area_min=entities.get("area_min"),
                        operation_type=entities.get("operation_type"),
                    ),
                    reasoning=data.get("reasoning")
                )
        except Exception as e:
            logger.error(f"Error al parsear respuesta: {e}")
        
        # Fallback
        return IntentClassification(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            extracted_entities=ExtractedEntities(),
            reasoning="No se pudo parsear la respuesta del LLM"
        )
    
    async def close(self):
        """Cierra conexión Redis."""
        if self._redis:
            await self._redis.close()


# Instancia global
intent_classifier = IntentClassifier()