"""
Clasificador de intents usando OpenAI GPT-4o-mini con response_format=json_object.
Elimina el parseo fragil de texto libre del clasificador anterior.
"""
import asyncio
import hashlib
import json
from typing import Optional
import redis.asyncio as redis
from loguru import logger
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.intent import Intent, INTENT_DESCRIPTIONS


class ExtractedEntities(BaseModel):
    budget_min: Optional[int] = Field(None)
    budget_max: Optional[int] = Field(None)
    location: Optional[str] = Field(None)
    property_type: Optional[str] = Field(None)
    bedrooms: Optional[int] = Field(None)
    bathrooms: Optional[int] = Field(None)
    area_min: Optional[int] = Field(None)
    operation_type: Optional[str] = Field(None)


class IntentClassification(BaseModel):
    intent: Intent = Field(...)
    confidence: float = Field(..., ge=0.0, le=1.0)
    extracted_entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    reasoning: Optional[str] = Field(None)


FEW_SHOT_EXAMPLES = """
Ejemplos:
1. "Hola, buenos dias" -> GREETING
2. "Quiero comprar una casa en Asuncion" -> PROPERTY_SEARCH (location=Asuncion, operation_type=venta)
3. "Busco departamento alquiler en Encarnacion hasta 500 USD" -> PROPERTY_SEARCH
4. "Presupuesto 200000 USD, casa 3 habitaciones en Posadas" -> PROPERTY_SEARCH
5. "Quiero saber mas detalles de la casa en Villa Edna" -> PROPERTY_DETAILS
6. "Cuantos metros tiene el terreno?" -> PROPERTY_DETAILS
7. "Quiero agendar una visita" -> SCHEDULE_APPOINTMENT
8. "Puedo ir a ver la casa manana a las 10?" -> SCHEDULE_APPOINTMENT
9. "Como funciona el proceso de compra?" -> FAQ
10. "Cobran comision?" -> FAQ
11. "Necesito hablar con un agente humano" -> HUMAN_HANDOFF
12. "Xyz123" -> UNKNOWN
"""

SYSTEM_PROMPT = """Eres un clasificador de mensajes para un chatbot de bienes raices.
Clasifica el mensaje en uno de estos intents:
{intent_list}

{examples}

Responde SOLO con JSON valido, sin texto adicional:
{{
  "intent": "NOMBRE_DEL_INTENT",
  "confidence": 0.0-1.0,
  "extracted_entities": {{
    "budget_min": numero o null,
    "budget_max": numero o null,
    "location": "texto o null",
    "property_type": "casa/departamento/terreno/oficina/local o null",
    "bedrooms": numero o null,
    "bathrooms": numero o null,
    "area_min": numero o null,
    "operation_type": "venta/alquiler o null"
  }},
  "reasoning": "breve explicacion"
}}"""


class IntentClassifier:
    """
    Clasificador de intents usando GPT-4o-mini.
    temperature=0 + response_format=json_object garantiza salida determinista.
    Cachea en Redis por 5 minutos.
    """

    CACHE_TTL = 300
    MAX_REDIS_RETRIES = 3

    def __init__(self):
        settings = get_settings()
        self._redis = None
        self._redis_url = settings.resolve_redis_url()

    def _get_client(self):
        from app.agents.cs_llm_client import get_client
        return get_client()

    def _get_model(self):
        from app.agents.cs_llm_client import get_model
        return get_model()

    async def _get_redis(self):
        for attempt in range(self.MAX_REDIS_RETRIES):
            try:
                if self._redis is None:
                    self._redis = redis.from_url(
                        self._redis_url,
                        decode_responses=True,
                        socket_connect_timeout=3,
                        socket_timeout=3,
                    )
                await self._redis.ping()
                return self._redis
            except Exception as e:
                logger.warning(f"[Classifier] Redis intento {attempt + 1}: {e}")
                await asyncio.sleep(0.5 * (2 ** attempt))
        return None

    def _cache_key(self, message):
        return f"intent:cache:{hashlib.md5(message.encode()).hexdigest()}"

    async def classify(self, message: str) -> IntentClassification:
        r = await self._get_redis()
        if r:
            try:
                cached = await r.get(self._cache_key(message))
                if cached:
                    logger.debug(f"[Classifier] Cache hit: {message[:40]!r}")
                    return IntentClassification.model_validate_json(cached)
            except Exception as e:
                logger.debug(f"[Classifier] Cache read error: {e}")

        classification = await self._call_openai(message)

        if r:
            try:
                await r.setex(self._cache_key(message), self.CACHE_TTL, classification.model_dump_json())
            except Exception as e:
                logger.debug(f"[Classifier] Cache write error: {e}")

        logger.info(
            f"[Classifier] intent={classification.intent.value} "
            f"confidence={classification.confidence:.2f}"
        )
        return classification

    async def _call_openai(self, message: str) -> IntentClassification:
        intent_list = "\n".join(f"- {i.value}: {INTENT_DESCRIPTIONS[i]}" for i in Intent)
        system = SYSTEM_PROMPT.format(intent_list=intent_list, examples=FEW_SHOT_EXAMPLES)
        try:
            client = self._get_client()
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._get_model(),
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": message},
                    ],
                    temperature=0.0,
                    max_completion_tokens=300,
                    response_format={"type": "json_object"},
                ),
                timeout=8.0,
            )
            raw = response.choices[0].message.content or "{}"
            return self._parse(raw)
        except Exception as e:
            logger.error(f"[Classifier] OpenAI error: {e}")
            return self._fallback()

    def _parse(self, raw: str) -> IntentClassification:
        try:
            data = json.loads(raw)
            intent_str = data.get("intent", "unknown").lower()
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.UNKNOWN
            entities = data.get("extracted_entities") or {}
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
                reasoning=data.get("reasoning"),
            )
        except Exception as e:
            logger.error(f"[Classifier] Parse error: {e} | raw={raw[:100]!r}")
            return self._fallback()

    @staticmethod
    def _fallback():
        return IntentClassification(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            extracted_entities=ExtractedEntities(),
            reasoning="Error en el clasificador",
        )

    async def close(self):
        if self._redis:
            await self._redis.close()


intent_classifier = IntentClassifier()
