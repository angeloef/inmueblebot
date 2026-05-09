"""
Cliente para OpenRouter API.
 Soporta modelos de Mistral, Llama, Qwen, y otros a través de OpenRouter.

Modelo primario: nemotron-3-super-120b-a12b:free (muy grande, 120B params)
"""
import asyncio
import json
import time
from typing import Optional, Any
import httpx
from loguru import logger

from app.core.config import get_settings
from app.agents.llm_router import LLMResponse, ToolCall


class OpenRouterClient:
    """
    Cliente async para OpenRouter.
    Soporta tool calling para modelos avanzados.
    """
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(self):
        settings = get_settings()
        self._api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
        self._model = getattr(settings, 'OPENROUTER_MODEL', '')
        self._timeout = settings.LLM_TIMEOUT_SECONDS
        self._max_retries = 2
        
        self._client: Optional[httpx.AsyncClient] = None
        
        if not self._api_key:
            logger.warning("OpenRouter: API key no configurada")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Obtiene cliente HTTP lazy."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
            )
        return self._client
    
    async def close(self):
        """Cierra el cliente HTTP."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _build_headers(self) -> dict:
        """Builds request headers."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://inmueblebot.app",
            "X-Title": "InmuebleBot"
        }
    
    async def ainvoke(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 1000
    ) -> LLMResponse:
        """
        Ejecuta una solicitud al LLM via OpenRouter.
        
        Args:
            messages: Lista de mensajes en formato OpenAI
            tools: Definiciones de herramientas (opcional)
            temperature: Temperatura (0.0-1.0)
            max_tokens: Máximo de tokens
        
        Returns:
            LLMResponse con contenido y tool calls
        """
        if not self._api_key:
            return LLMResponse(
                content="",
                error="OpenRouter API key no configurada",
                provider="openrouter"
            )
        
        start_time = time.time()
        last_error = None
        
        for attempt in range(self._max_retries + 1):
            try:
                payload = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"
                
                client = await self._get_client()
                
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=self._build_headers(),
                    json=payload
                )
                
                latency = time.time() - start_time
                logger.info(f"[OpenRouter] Latencia: {latency:.2f}s")
                
                if response.status_code == 429:
                    logger.warning(f"[OpenRouter] Rate limit (attempt {attempt + 1})")
                    if attempt < self._max_retries:
                        wait_time = (attempt + 1) * 2
                        logger.info(f"[OpenRouter] Esperando {wait_time}s antes de reintentar...")
                        await asyncio.sleep(wait_time)
                    continue
                
                if response.status_code == 503:
                    logger.warning(f"[OpenRouter] Modelo no disponible (attempt {attempt + 1})")
                    if attempt < self._max_retries:
                        await asyncio.sleep(2)
                    continue
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"[OpenRouter] Error {response.status_code}: {error_text[:200]}")
                    return LLMResponse(
                        content="",
                        error=f"OpenRouter error {response.status_code}",
                        provider="openrouter"
                    )
                
                data = response.json()
                
                if not data.get("choices"):
                    return LLMResponse(
                        content="",
                        error="OpenRouter: respuesta vacía",
                        provider="openrouter"
                    )
                
                choice = data["choices"][0]
                message = choice.get("message", {})
                
                content = message.get("content", "")
                tool_calls = []
                
                if message.get("tool_calls"):
                    for tc in message["tool_calls"]:
                        try:
                            func = tc.get("function", {})
                            args = json.loads(func.get("arguments", "{}"))
                            tool_calls.append(ToolCall(
                                name=func.get("name", "unknown"),
                                arguments=args
                            ))
                        except json.JSONDecodeError as e:
                            logger.warning(f"[OpenRouter] Error parseando tool call: {e}")
                
                usage = data.get("usage", {})
                
                return LLMResponse(
                    content=content,
                    tool_calls=tool_calls,
                    finish_reason=choice.get("finish_reason", "stop"),
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "latency_seconds": latency
                    },
                    provider="openrouter"
                )
                
            except asyncio.TimeoutError:
                last_error = "timeout"
                logger.warning(f"[OpenRouter] Timeout (attempt {attempt + 1})")
                if attempt < self._max_retries:
                    await asyncio.sleep(2)
                    
            except httpx.ConnectError as e:
                last_error = "connection"
                logger.warning(f"[OpenRouter] Connection error: {e}")
                if attempt < self._max_retries:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"[OpenRouter] Error inesperado: {e}")
                if attempt < self._max_retries:
                    await asyncio.sleep(2)
        
        return LLMResponse(
            content="",
            error=last_error or "OpenRouter falló todos los intentos",
            provider="openrouter"
        )


openrouter_client = OpenRouterClient()