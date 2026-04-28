"""
Multi-LLM Router con fallback automático.

Priority (working order):
1. Gemini 2.5 Flash (PRIMARY - best tool calling)
2. OpenRouter (Grok/minimax) - fallback
3. MiniMax via OpenRouter - last resort
4. Fallback message

Providers:
- gemini: Google Gemini 2.5 Flash (primary)
- minimax: MiniMax M2.5 via OpenRouter (fallback)
- openrouter: Grok (backup)
- fallback: Simple error response
"""
import asyncio
import time
from typing import Optional
from loguru import logger

from app.core.config import get_settings
from app.agents.llm import AsyncMiniMaxClient, LLMResponse as MiniMaxResponse
from app.agents.gemini_client import GeminiClient, LLMResponse as GeminiResponse


# Alias para respuesta unificada
class ToolCall:
    """Representa una llamada a herramienta retornada por el LLM."""
    
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments
    
    def __repr__(self):
        return f"ToolCall(name={self.name}, args={self.arguments})"


class LLMResponse:
    """Respuesta unificada de cualquier LLM."""
    
    def __init__(
        self,
        content: str = "",
        tool_calls: list = None,
        finish_reason: str = "stop",
        usage: dict = None,
        provider: str = "unknown",
        error: str = None
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.usage = usage or {}
        self.provider = provider
        self.error = error
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
    
    @property
    def is_error(self) -> bool:
        return self.error is not None or not self.content
    
    def __repr__(self):
        return f"LLMResponse(provider={self.provider}, has_tool_calls={self.has_tool_calls}, content={self.content[:50]}...)"


class LLMRouter:
    """
    Router with fallback: Gemini 2.5 Flash -> OpenRouter -> MiniMax -> Fallback
    
    Priority: 1) Gemini 2.5 Flash (primary - best tool calling), 2) OpenRouter (Grok), 3) MiniMax (last resort), 4) Fallback
    """
    
    # Providers in priority order - Gemini 2.5 Flash first, then OpenRouter, then MiniMax
    PROVIDERS = ["gemini", "openrouter", "minimax"]
    
    #_ERRORES que triggers fallback
    RETRYABLE_ERRORS = {
        "timeout", "503", "429", "connection", "rate_limit",
        "unavailable", "empty_response", "api_error", "502", "504"
    }
    
    # Categorías de error para logging
    ERROR_CATEGORIES = {
        "rate_limit": ["429", "rate_limit", "rate limit", "quota"],
        "timeout": ["timeout", "timed out", "504"],
        "connection": ["connection", "network", "503"],
        "content_filter": ["content", "filter", "safety"],
        "auth": ["401", "unauthorized", "api key"]
    }
    
    def __init__(self):
        settings = get_settings()
        self._timeout = settings.LLM_TIMEOUT_SECONDS
        self._max_retries = settings.LLM_MAX_RETRIES
        self._default_temperature = settings.LLM_TEMPERATURE
        self._default_max_tokens = settings.LLM_MAX_TOKENS
        
        # Inicializar clientes
        from app.agents.openrouter_client import OpenRouterClient
        self._openrouter = OpenRouterClient()
        self._gemini = GeminiClient()
        self._minimax = AsyncMiniMaxClient()
        
        # Estado de salud de proveedores
        self._provider_health = {
            "openrouter": True,
            "gemini": True,
            "minimax": True
        }
        
        # Contador de uso
        self._request_count = {"openrouter": 0, "gemini": 0, "minimax": 0}
        
        # Latencia por proveedor
        self._latency = {"openrouter": None, "gemini": None, "minimax": None}
        
        logger.info("=== LLMRouter inicializado ===")
        logger.info("Prioridad: 1) Gemini 2.5 Flash, 2) OpenRouter, 3) MiniMax")
    
    def _classify_error(self, error: str) -> str:
        """Clasifica el tipo de error."""
        error_lower = error.lower()
        for category, patterns in self.ERROR_CATEGORIES.items():
            if any(p in error_lower for p in patterns):
                return category
        return "unknown"
    
    async def ainvoke(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = None,
        max_tokens: int = None,
        forced_provider: str = None
    ) -> LLMResponse:
        """
        Ejecuta una solicitud al LLM con fallback automático.
        
        Args:
            messages: Lista de mensajes
            tools: Definiciones de herramientas (opcional)
            temperature: Temperatura
            max_tokens: Máximo de tokens
            forced_provider: Forzar uso de un proveedor específico
        
        Returns:
            LLMResponse con contenido y metadatos
        """
        temperature = temperature or self._default_temperature
        max_tokens = max_tokens or self._default_max_tokens
        
        providers_to_try = [forced_provider] if forced_provider else self.PROVIDERS
        
        last_error = None
        error_category = "unknown"
        
        for provider in providers_to_try:
            if not self._provider_health.get(provider, False):
                logger.info(f"Saltando {provider} (marcado como no saludable)")
                continue
            
            # Mostrar qué proveedor se usa
            if provider == "gemini":
                logger.info("[LLM] Using: Gemini 2.5 Flash (PRIMARY)")
            elif provider == "openrouter":
                logger.info("[LLM] Using: OpenRouter (fallback)")
            elif provider == "minimax":
                logger.info("[LLM] Using: MiniMax (last resort)")
            
            for attempt in range(self._max_retries + 1):
                try:
                    logger.debug(f"Intentando {provider} (attempt {attempt + 1}/{self._max_retries + 1})")
                    
                    if provider == "openrouter":
                        response = await self._call_openrouter(
                            messages, tools, temperature, max_tokens
                        )
                    elif provider == "gemini":
                        response = await self._call_gemini(
                            messages, tools, temperature, max_tokens
                        )
                    elif provider == "minimax":
                        response = await self._call_minimax(
                            messages, tools, temperature, max_tokens
                        )
                    else:
                        continue
                    
                    # Verificar si la respuesta es válida
                    if self._is_valid_response(response):
                        self._request_count[provider] += 1
                        logger.info(f"✓ {provider.upper()} responded successfully")
                        return response
                    
                    # Respuesta inválida → retry
                    last_error = f"Empty response from {provider}"
                    logger.warning(f"✗ {provider} returned empty content, retrying...")
                    
                except Exception as e:
                    last_error = str(e)
                    error_category = self._classify_error(last_error)
                    logger.warning(f"✗ Error with {provider}: {error_category} - {e}")
                    
                    # Rate limit específico
                    if error_category == "rate_limit":
                        logger.warning(f"Rate limit detected for {provider}")
                    
                    # Content filter
                    if error_category == "content_filter":
                        logger.warning(f"Content filter triggered for {provider}")
                
                # Exponential backoff antes de reintentar
                if attempt < self._max_retries:
                    wait_time = (2 ** attempt) + 1  # +1 second minimum
                    logger.debug(f"Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
            
            # Si todos los intentos fallan para este proveedor
            logger.warning(f"⚠ {provider} failed after {self._max_retries + 1} attempts")
            
            # Delay before fallback
            if provider == "gemini":
                logger.info("Gemini failed → falling back to MiniMax M2.5")
                await asyncio.sleep(1.5)  # Small delay before fallback
            
            self._provider_health[provider] = False
            last_error = f"All attempts with {provider} failed"
        
        # Si llegamos aquí, todos los proveedores fallaron
        logger.error("❌ All LLM providers failed")
        logger.info("Both LLMs failed → using fallback message")
        
        return LLMResponse(
            content="Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos segundos.",
            provider="fallback",
            error="all_providers_failed"
        )
    
    async def _call_openrouter(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int
    ) -> LLMResponse:
        """Llama a OpenRouter (Nemotron) con manejo de errores."""
        import time
        start_time = time.time()
        
        try:
            response = await self._openrouter.ainvoke(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            latency = time.time() - start_time
            self._latency["openrouter"] = latency
            
            if response.usage:
                response.usage["latency_seconds"] = latency
            
            return LLMResponse(
                content=response.content,
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
                usage=response.usage,
                provider="openrouter"
            )
        except Exception as e:
            logger.error(f"Error in OpenRouter call: {e}")
            raise
    
    async def _call_minimax(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int
    ) -> LLMResponse:
        """Llama a MiniMax con manejo de errores."""
        try:
            response = await self._minimax.ainvoke(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return LLMResponse(
                content=response.content,
                tool_calls=response.tool_calls,
                finish_reason=response.finish_reason,
                usage=response.usage,
                provider="minimax"
            )
        except Exception as e:
            logger.error(f"Error in MiniMax call: {e}")
            raise
    
    async def _call_gemini(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int
    ) -> LLMResponse:
        """Llama a Gemini con manejo de errores y retry sin tools."""
        
        for attempt in range(2):
            try:
                logger.debug(f"[Gemini] Attempt {attempt + 1}, tools={'enabled' if tools else 'disabled'}")
                
                response = await self._gemini.ainvoke(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                if response.error:
                    error_msg = str(response.error)
                    logger.warning(f"[Gemini] Error response: {error_msg}")
                    
                    if "400" in error_msg and tools:
                        logger.warning(f"[Gemini] 400 error with tools: {error_msg[:100]}")
                        logger.info("[Gemini] Attempting retry with tool format correction...")
                        # Don't disable tools entirely - the client handles format correction internally
                        # Just pass tools as-is and let gemini_client handle the fallback
                        continue
                    
                    if "429" in error_msg or "503" in error_msg:
                        logger.warning(f"[Gemini] Rate limited or unavailable: {error_msg}")
                        raise Exception(error_msg)
                
                return LLMResponse(
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                    finish_reason=response.finish_reason,
                    usage=response.usage,
                    provider="gemini"
                )
                
            except Exception as e:
                error_str = str(e)
                logger.warning(f"[Gemini] Attempt {attempt + 1} failed: {error_str}")
                
                if "400" in error_str and tools:
                    logger.info("[Gemini] 400 error, reintentando sin tools...")
                    tools = None
                    continue
                raise
    
    def _is_valid_response(self, response: LLMResponse) -> bool:
        """Verifica si la respuesta es válida."""
        if response.error:
            logger.warning(f"[Router] Response tiene error: {response.error}")
            return False
        
        if not response.content or len(response.content.strip()) == 0:
            if not response.tool_calls:
                return False
        
        return True
    
    async def chat(
        self,
        message: str,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> str:
        """Chat simple sin tool calling."""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": message})
        
        response = await self.ainvoke(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.content
    
    def get_stats(self) -> dict:
        """Retorna estadísticas de uso."""
        return {
            "provider_health": self._provider_health.copy(),
            "request_count": self._request_count.copy()
        }
    
    async def check_health(self) -> dict:
        """
        Verifica la salud de todos los proveedores.
        
        Returns:
            Dict con estado de cada proveedor
        """
        results = {}
        
        # Test MiniMax (primary)
        try:
            response = await self._call_minimax(
                [{"role": "user", "content": "Hi"}],
                None, 0.7, 10
            )
            results["minimax"] = {
                "status": "healthy" if response.content else "degraded",
                "response": response.content[:100] if response.content else "empty"
            }
        except Exception as e:
            results["minimax"] = {"status": "unhealthy", "error": str(e)}
        
        # Test Gemini (backup)
        try:
            response = await self._call_gemini(
                [{"role": "user", "content": "Hi"}],
                None, 0.7, 10
            )
            results["gemini"] = {
                "status": "healthy" if response.content else "degraded",
                "response": response.content[:100] if response.content else "empty"
            }
        except Exception as e:
            results["gemini"] = {"status": "unhealthy", "error": str(e)}
        
        # Test OpenRouter (fallback)
        try:
            response = await self._call_openrouter(
                [{"role": "user", "content": "Hi"}],
                None, 0.7, 10
            )
            results["openrouter"] = {
                "status": "healthy" if response.content else "degraded",
                "response": response.content[:100] if response.content else "empty"
            }
        except Exception as e:
            results["openrouter"] = {"status": "unhealthy", "error": str(e)}
        
        return results
    
    def reset_health(self):
        """Reinicia el estado de salud."""
        self._provider_health = {"gemini": True, "minimax": True}
        logger.info("Provider health status reset")


# Instancia global
llm_router = LLMRouter()