"""
Cliente para Google Gemini 2.5 Flash usando el nuevo SDK google-genai.
Soporte nativo de tool calling con la API de Google.
"""
import json
import asyncio
from typing import Optional, Any
from loguru import logger

from google import genai
from google.genai import types

from app.core.config import get_settings


class ToolCall:
    """Representa una llamada a herramienta retornada por el LLM."""
    
    def __init__(self, name: str, arguments: dict, id: str = ""):
        self.name = name
        self.arguments = arguments
        self.id = id
    
    def __repr__(self):
        return f"ToolCall(name={self.name}, id={self.id}, args={self.arguments})"


class LLMResponse:
    """Respuesta unificada del LLM."""
    
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


class GeminiClient:
    """
    Cliente para Google Gemini 2.5 Flash usando el nuevo SDK (google.genai).
    """
    
    def __init__(self):
        settings = get_settings()
        self._api_key = settings.GEMINI_API_KEY
        self._model = settings.GEMINI_MODEL
        self._timeout = settings.LLM_TIMEOUT_SECONDS
        self._client: Optional[genai.Client] = None
        
        if not self._api_key:
            logger.warning("GEMINI_API_KEY no configurada")
            return
        
        self._client = genai.Client(api_key=self._api_key)
        logger.info(f"[Gemini] Client initialized with model: {self._model}")
    
    def _convert_langchain_tools_to_gemini(self, tools: list[dict]) -> list[types.Tool]:
        """
        Convierte herramientas en formato LangChain a formato de Google Tool.
        
        LangChain format:
        [{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}]
        
        Google genai format:
        types.Tool(function_declarations=[...])
        """
        gemini_tools = []
        
        for tool in tools:
            func_def = tool.get("function", {})
            if not func_def:
                continue
            
            name = func_def.get("name")
            description = func_def.get("description", "")
            parameters = func_def.get("parameters")
            
            if not name:
                continue
            
            param_schema = None
            if parameters and parameters.get("type") == "object":
                from google.genai.types import Schema
                properties = {}
                for k, v in parameters.get("properties", {}).items():
                    properties[k] = Schema(
                        type="STRING",
                        description=v.get("description", "")
                    )
                param_schema = Schema(
                    type="OBJECT",
                    properties=properties,
                    required=parameters.get("required", [])
                )
            
            func_decl = types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=param_schema
            )
            gemini_tools.append(types.Tool(function_declarations=[func_decl]))
        
        return gemini_tools
    
    async def ainvoke(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = 0.4,
        max_tokens: int = 1200
    ) -> LLMResponse:
        """
        Envía una solicitud a Gemini 2.5 Flash con tool calling.
        """
        if not self._api_key:
            logger.warning("GEMINI_API_KEY no configurada")
            return LLMResponse(
                content="El servicio de IA no está disponible.",
                error="API key missing",
                provider="gemini"
            )
        
        try:
            return await self._ainvoke_async(messages, tools, temperature, max_tokens)
        except Exception as e:
            logger.error(f"[Gemini] Error: {e}")
            return LLMResponse(
                content="",
                error=str(e),
                provider="gemini"
            )
    
    async def _ainvoke_async(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int
    ) -> LLMResponse:
        """Implementación async con el nuevo SDK google.genai."""
        
        tools_count = len(tools) if tools else 0
        tool_names = [t.get("function", {}).get("name") for t in (tools or [])]
        logger.info(f"[Gemini] Model: {self._model}, Tools: {tools_count} - {tool_names}")
        
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                role = "user"
            if role == "assistant":
                role = "model"
            
            if role == "tool":
                tool_name = msg.get("name") or msg.get("tool_call_id", "")
                tool_id = msg.get("tool_call_id", "")
                if not tool_name:
                    logger.warning(f"[Gemini] Tool message missing name field: {msg.keys()}")
                    continue
                # Use proper FunctionResponse type with id
                try:
                    from google.genai.types import FunctionResponse
                    fr = FunctionResponse(
                        id=tool_id,
                        name=tool_name,
                        response={"result": content}
                    )
                    part = types.Part(function_response=fr)
                except Exception:
                    # Fallback to dict format
                    part = types.Part(
                        function_response={
                            "id": tool_id,
                            "name": tool_name,
                            "response": {"result": content}
                        }
                    )
            else:
                part = types.Part(text=str(content))
            
            contents.append(types.Content(role=role, parts=[part]))
        
        gemini_tools = None
        if tools:
            try:
                gemini_tools = self._convert_langchain_tools_to_gemini(tools)
            except Exception as e:
                logger.warning(f"[Gemini] Tool conversion error: {e}")
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            top_p=0.95,
            tools=gemini_tools,
        )
        
        response = None
        max_retries = 3
        retry_count = 0
        tools_disabled = False
        
        while retry_count < max_retries:
            def generate():
                return self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config
                )
            
            try:
                response = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, generate),
                    timeout=self._timeout
                )
                break
            except Exception as e:
                error_str = str(e)
                retry_count += 1
                
                if "503" in error_str and "high demand" in error_str.lower():
                    if retry_count < max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(f"[Gemini] 503 high demand, retry {retry_count}/{max_retries} in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error("[Gemini] 503 high demand - all retries exhausted")
                        return LLMResponse(
                            content="El servicio de Gemini está saturado. Intentando con otro proveedor...",
                            error="503_high_demand",
                            provider="gemini"
                        )
                elif "429" in error_str or "rate" in error_str.lower():
                    if retry_count < max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(f"[Gemini] 429 rate limit, retry {retry_count}/{max_retries} in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error("[Gemini] 429 rate limit - all retries exhausted")
                        return LLMResponse(
                            content="El servicio tiene mucho tráfico.",
                            error="429",
                            provider="gemini"
                        )
                elif "400" in error_str and config.tools and not tools_disabled:
                    logger.info("[Gemini] Tool format error, retrying without tools")
                    config.tools = None
                    tools_disabled = True
                    continue
                else:
                    logger.error(f"[Gemini] Error: {error_str}")
                    return LLMResponse(content="", error=error_str[:200], provider="gemini")
        
        if retry_count >= max_retries and response is None:
            return LLMResponse(
                content="",
                error="max_retries_exceeded",
                provider="gemini"
            )
        
        content_text = ""
        tool_calls = []
        
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.text:
                    content_text += part.text
                
                if part.function_call:
                    func = part.function_call
                    args = {}
                    if hasattr(func, 'args') and func.args:
                        try:
                            args = dict(func.args) if hasattr(func.args, 'items') else json.loads(func.args) if isinstance(func.args, str) else {}
                        except:
                            args = {"raw_args": str(func.args)}
                    
                    # Get ID if available
                    tool_id = getattr(func, 'id', None) or ""
                    
                    tool_calls.append(ToolCall(
                        name=func.name, 
                        arguments=args,
                        id=tool_id
                    ))
                    logger.info(f"[Gemini] ✓ Tool call: {func.name} (id: {tool_id})")
        
        usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "prompt_tokens": getattr(um, 'prompt_token_count', 0),
                "candidates_tokens": getattr(um, 'candidates_token_count', 0),
                "total_tokens": getattr(um, 'total_token_count', 0)
            }
        
        finish_reason = "stop"
        if response.candidates:
            finish_reason = str(getattr(response.candidates[0], 'finish_reason', 'stop'))
        
        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            provider="gemini"
        )


gemini_client = GeminiClient()


async def test_gemini():
    """Test function to verify Gemini 2.5 Flash tool calling works."""
    from app.agents.prompts import TOOL_DEFINITIONS
    
    client = GeminiClient()
    
    print(f"\n{'='*50}")
    print(f"[Gemini Test] Model: {client._model}")
    print(f"{'='*50}")
    
    tools_sent = len(TOOL_DEFINITIONS) if TOOL_DEFINITIONS else 0
    tool_names = [t.get('function', {}).get('name') for t in TOOL_DEFINITIONS]
    print(f"[Gemini Test] Tools: {tools_sent} - {tool_names}")
    
    try:
        messages = [
            {"role": "user", "content": "busco una casa de 4 habitaciones en obera"}
        ]
        
        response = await client.ainvoke(
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0.4,
            max_tokens=1200
        )
        
        print(f"\n[Gemini Test] Result:")
        print(f"  Provider: {response.provider}")
        print(f"  Tools called: {response.has_tool_calls}")
        
        if response.has_tool_calls:
            print(f"  ✓ Tool calls:")
            for tc in response.tool_calls:
                print(f"    - {tc.name}: {tc.arguments}")
        else:
            print(f"  Response: {response.content[:200] if response.content else '(empty)'}")
        
        if response.error:
            print(f"  ✗ Error: {response.error}")
        
        success = not response.error and response.has_tool_calls
        print(f"\n{'='*50}")
        print(f"[Gemini Test] Tool Calling: {'✓ WORKING' if success else '✗ FAILED'}")
        print(f"{'='*50}")
        
        return response
        
    except Exception as e:
        print(f"[Gemini Test] Exception: {e}")
        raise


async def test_gemini_no_tools():
    """Test basic generation without tools."""
    from app.agents.prompts import TOOL_DEFINITIONS
    
    client = GeminiClient()
    
    if not client._api_key:
        print("GEMINI_API_KEY not set")
        return LLMResponse(error="no_api_key")
    
    messages = [{"role": "user", "content": "Hola, cómo estás?"}]
    
    print(f"[BASIC] Testing basic generation...")
    
    response = await client.ainvoke(
        messages=messages,
        tools=None,  # No tools for basic test
        temperature=0.4,
        max_tokens=200
    )
    
    return response


if __name__ == "__main__":
    asyncio.run(test_gemini())