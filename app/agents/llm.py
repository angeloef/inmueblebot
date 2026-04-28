"""
Cliente LLM para MiniMax M2.5 via OpenRouter.
Soporta tool calling / function calling.
"""
from typing import Optional, Any, Callable
import json
import httpx
from loguru import logger

from app.core.config import get_settings


class ToolCall:
    """Representa una llamada a herramienta retornada por el LLM."""
    
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments
    
    def __repr__(self):
        return f"ToolCall(name={self.name}, args={self.arguments})"


class LLMResponse:
    """Respuesta del LLM con soporte para tool calls."""
    
    def __init__(
        self,
        content: str = "",
        tool_calls: list[ToolCall] = None,
        finish_reason: str = "stop",
        usage: dict = None
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.usage = usage or {}
    
    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class AsyncMiniMaxClient:
    """
    Cliente async para MiniMax M2.5 via OpenRouter.
    
    Soporta:
    - Chat básico
    - Tool calling / function calling
    - Historial de mensajes
    - Manejo de errores con fallback
    
    MiniMax M2.5 usa el formato de tool calling de OpenAI:
    https://platform.openai.com/docs/guides/function-calling
    """
    
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.MINIMAX_API_KEY or settings.OPENROUTER_API_KEY
        self._model = settings.MINIMAX_MODEL
        self._base_url = "https://openrouter.ai/api/v1"
        self._default_headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://inmueblebot.com",
            "X-Title": "InmuebleBot"
        }
    
    async def ainvoke(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        tool_choice: str = "auto"
    ) -> LLMResponse:
        """
        Envía una solicitud al LLM con soporte para tool calling.
        
        Args:
            messages: Lista de mensajes [{"role": "system|user|assistant|tool", "content": "..."}]
            tools: Lista de definiciones de herramientas en formato OpenAI
            temperature: Temperatura de generación (0.0 - 1.0)
            max_tokens: Máximo de tokens en respuesta
            tool_choice: "auto", "none", o {"type": "function", "function": {"name": "..."}}
        
        Returns:
            LLMResponse con contenido y/o tool_calls
        """
        if not self._api_key:
            logger.warning("MINIMAX_API_KEY no configurada")
            return LLMResponse(
                content="Lo siento, el servicio de IA no está disponible en este momento."
            )
        
        url = f"{self._base_url}/chat/completions"
        
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._default_headers
                )
                
                if response.status_code == 503:
                    logger.warning("OpenRouter API 503 - servicio no disponible")
                    raise Exception("503 Service Unavailable")
                
                if response.status_code == 429:
                    logger.warning("OpenRouter API 429 - rate limit")
                    raise Exception("429 Rate Limit")
                
                response.raise_for_status()
                data = response.json()
                
                return self._parse_response(data)
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP del LLM: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP {e.response.status_code}")
        except httpx.TimeoutException:
            logger.error("Timeout al llamar al LLM")
            raise Exception("Timeout")
        except Exception as e:
            logger.error(f"Error al llamar al LLM: {e}")
            raise
    
    def _parse_response(self, data: dict) -> LLMResponse:
        """Parsea la respuesta de la API de OpenRouter."""
        try:
            message = data["choices"][0]["message"]
            content = message.get("content", "")
            
            tool_calls = []
            if "tool_calls" in message:
                for tc in message["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    arguments = json.loads(func.get("arguments", "{}"))
                    tool_calls.append(ToolCall(name=name, arguments=arguments))
            
            usage = data.get("usage", {})
            finish_reason = data["choices"][0].get("finish_reason", "stop")
            
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage
            )
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error al parsear respuesta del LLM: {e}")
            return LLMResponse(content="Error al procesar la respuesta del servidor.")
    
    async def chat(
        self,
        message: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        """
        Chat simple sin tool calling.
        
        Args:
            message: Mensaje del usuario
            system_prompt: Prompt del sistema
            temperature: Temperatura
            max_tokens: Máximo de tokens
        
        Returns:
            Respuesta como string
        """
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
    
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_handler: Callable[[str, dict], Any],
        max_tool_calls: int = 5,
        temperature: float = 0.7
    ) -> str:
        """
        Ejecuta un chat con tool calling automático.
        
        Maneja la ejecución de herramientas y continúa la conversación
        hasta que el LLM no haga más llamadas a herramientas.
        
        Args:
            messages: Historial de mensajes
            tools: Definiciones de herramientas
            tool_handler: Función async que ejecuta la herramienta
            max_tool_calls: Máximo de tool calls por turno
            temperature: Temperatura
        
        Returns:
            Respuesta final del LLM
        """
        all_messages = messages.copy()
        
        for iteration in range(max_tool_calls):
            response = await self.ainvoke(
                messages=all_messages,
                tools=tools,
                temperature=temperature
            )
            
            if not response.has_tool_calls:
                return response.content
            
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_args = tool_call.arguments
                
                logger.info(f"Ejecutando tool: {tool_name} con args: {tool_args}")
                
                try:
                    tool_result = await tool_handler(tool_name, tool_args)
                except Exception as e:
                    tool_result = f"Error al ejecutar {tool_name}: {str(e)}"
                    logger.error(f"Error en tool {tool_name}: {e}")
                
                all_messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{iteration}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args)
                            }
                        }
                    ]
                })
                
                all_messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "tool_call_id": f"call_{iteration}",
                    "content": str(tool_result)
                })
        
        logger.warning(f"Alcanzó máximo de tool calls: {max_tool_calls}")
        return "Hubo un problema al procesar tu solicitud. ¿Podrías intentar de nuevo?"
    
    async def chat_with_history(
        self,
        messages: list[dict],
        system_prompt: str = None,
        temperature: float = 0.7
    ) -> str:
        """
        Chat con historial de mensajes.
        
        Args:
            messages: Lista de mensajes
            system_prompt: Prompt del sistema
            temperature: Temperatura
        
        Returns:
            Respuesta del LLM
        """
        all_messages = []
        
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        
        all_messages.extend(messages)
        
        response = await self.ainvoke(
            messages=all_messages,
            temperature=temperature
        )
        
        return response.content


def format_tool_definition(
    name: str,
    description: str,
    parameters: dict
) -> dict:
    """
    Crea una definición de herramienta en formato OpenAI.
    
    Args:
        name: Nombre de la función
        description: Descripción de lo que hace
            parameters: Esquema JSON de parámetros (tipo object con properties)
        
        Returns:
            Diccionario de definición de tool
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters
        }
    }


# Instancia global del cliente
minimax_client = AsyncMiniMaxClient()