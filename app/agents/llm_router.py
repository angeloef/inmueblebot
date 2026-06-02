"""
LLM Router - OpenAI GPT-4o-mini (unico proveedor).

Interfaz publica mantenida igual:
  - LLMResponse, ToolCall, LLMRouter.ainvoke(), llm_router (instancia global)
"""
import asyncio
import json
import time
from typing import Optional, List, Dict, Any
from loguru import logger

from app.core.config import get_settings


class ToolCall:
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments

    def __repr__(self):
        return f"ToolCall(name={self.name!r}, args={self.arguments})"


class LLMResponse:
    def __init__(
        self,
        content: str = "",
        tool_calls=None,
        finish_reason: str = "stop",
        usage: dict = None,
        provider: str = "openai",
        error: str = None,
        structured: Any = None,  # v2.0: parsed AgentResponse
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.usage = usage or {}
        self.provider = provider
        self.error = error
        self.structured = structured  # v2.0: AgentResponse or None

    @property
    def has_tool_calls(self):
        return len(self.tool_calls) > 0

    @property
    def is_error(self):
        return self.error is not None

    def __repr__(self):
        return (
            f"LLMResponse(provider={self.provider!r}, "
            f"has_tool_calls={self.has_tool_calls}, "
            f"content={self.content[:60]!r})"
        )


class LLMRouter:
    """Cliente LLM multi-proveedor via interfaz OpenAI-compatible."""

    _RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(self):
        settings = get_settings()
        self._timeout = settings.LLM_TIMEOUT_SECONDS
        self._max_retries = settings.LLM_MAX_RETRIES
        self._default_temperature = settings.LLM_TEMPERATURE
        self._default_max_completion_tokens = settings.LLM_MAX_TOKENS
        self._client = None

        from app.agents.cs_llm_client import get_model
        logger.info(f"LLMRouter inicializado -> proveedor: {settings.LLM_PROVIDER} / modelo: {get_model()}")

    def _get_client(self):
        from app.agents.cs_llm_client import get_client
        return get_client()

    async def ainvoke(
        self,
        messages,
        tools=None,
        temperature=None,
        max_completion_tokens=None,
        forced_provider=None,
        response_format=None,
        structured_response: bool = False,  # v2.0: enforce AgentResponse schema
    ):
        from app.agents.cs_llm_client import get_model, supports_strict_json_schema

        temperature = temperature if temperature is not None else self._default_temperature
        max_completion_tokens = max_completion_tokens or self._default_max_completion_tokens
        client = self._get_client()

        kwargs = {
            "model": get_model(),
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        # v2.0: Structured output — enforce AgentResponse JSON schema
        if structured_response:
            if supports_strict_json_schema():
                from app.agents.schemas import AGENT_RESPONSE_JSON_SCHEMA
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": AGENT_RESPONSE_JSON_SCHEMA,
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}
            logger.debug(f"[LLM] structured output enabled (provider={get_settings().LLM_PROVIDER})")

        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                start = time.time()
                logger.debug(
                    f"[OpenAI] attempt {attempt + 1}/{self._max_retries + 1} "
                    f"model={self._model} tools={'yes' if tools else 'no'}"
                )
                response = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=self._timeout,
                )
                latency = time.time() - start
                logger.info(f"[OpenAI] respuesta en {latency:.1f}s")
                llm_resp = self._parse_response(response, latency)

                # v2.0: Parse structured AgentResponse from text content
                if structured_response and not llm_resp.has_tool_calls and llm_resp.content:
                    from app.agents.schemas import AgentResponse
                    try:
                        parsed = json.loads(llm_resp.content)
                        llm_resp.structured = AgentResponse.model_validate(parsed)
                        logger.info(
                            f"[OpenAI] v2.0 structured: action={llm_resp.structured.action} "
                            f"confidence={llm_resp.structured.confidence}"
                        )
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(
                            f"[OpenAI] v2.0 structured parse failed: {e}. "
                            f"Raw content: {llm_resp.content[:200]}"
                        )
                        # Build fallback inline to avoid import-in-except issues
                        llm_resp.structured = AgentResponse(
                            action="respond",
                            response="Disculpá, tuve un problema técnico. ¿Podrías repetirme lo que necesitás?",
                            confidence=0.0,
                            reasoning=f"Parse error: {str(e)[:100]}",
                        )

                return llm_resp

            except asyncio.TimeoutError:
                last_error = f"Timeout despues de {self._timeout}s"
                logger.warning(f"[OpenAI] {last_error}")

            except Exception as e:
                last_error = str(e)
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in self._RETRYABLE_STATUS:
                    logger.warning(f"[OpenAI] Error {status} - reintentando: {e}")
                else:
                    logger.error(f"[OpenAI] Error no retriable: {e}")
                    break

            if attempt < self._max_retries:
                wait = 2 ** attempt
                await asyncio.sleep(wait)

        logger.error(f"[OpenAI] Todos los intentos fallaron. Ultimo error: {last_error}")
        return LLMResponse(
            content="Lo siento, estoy teniendo problemas tecnicos. Por favor intenta de nuevo.",
            provider="openai",
            error=last_error,
        )

    def _parse_response(self, response, latency=0.0):
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason or "stop"

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(name=tc.function.name, arguments=args))
            logger.info(f"[OpenAI] Tool calls: {[tc.name for tc in tool_calls]}")

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "latency_seconds": latency,
            }

        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            provider="openai",
        )

    async def chat(self, message, system_prompt=None, temperature=None, max_completion_tokens=None, response_format=None, return_usage=False):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})
        response = await self.ainvoke(
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            response_format=response_format,
        )
        if return_usage:
            return response.content, response.usage
        return response.content

    def get_stats(self):
        return {"provider": "openai", "model": self._model}

    async def check_health(self):
        try:
            r = await self.ainvoke(messages=[{"role": "user", "content": "ping"}], max_completion_tokens=5)
            if r.error:
                return {"status": "unhealthy", "error": r.error}
            return {"status": "healthy", "model": self._model}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def reset_health(self):
        pass


llm_router = LLMRouter()
