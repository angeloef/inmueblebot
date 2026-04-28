"""
Tests para el router de LLMs con fallback.
Ejecutar: pytest tests/test_llm_router.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.agents.llm_router import LLMRouter, LLMResponse


class TestLLMRouter:
    """Tests para el LLMRouter."""
    
    @pytest.fixture
    def router(self):
        """Fixture que retorna un router con clientes mockeados."""
        with patch("app.agents.llm_router.AsyncMiniMaxClient"):
            with patch("app.agents.llm_router.GeminiClient"):
                return LLMRouter()
    
    @pytest.mark.asyncio
    async def test_primary_provider_success(self, router):
        """Test cuando el proveedor primario responde correctamente."""
        mock_response = LLMResponse(
            content="Hola, ¿en qué puedo ayudarte?",
            provider="minimax"
        )
        
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = MagicMock(
                content="Hola, ¿en qué puedo ayudarte?",
                tool_calls=[],
                finish_reason="stop",
                usage={}
            )
            
            response = await router.ainvoke(
                messages=[{"role": "user", "content": "Hola"}]
            )
            
            assert "ayudarte" in response.content
            assert response.provider == "minimax"
    
    @pytest.mark.asyncio
    async def test_fallback_on_minimax_failure(self, router):
        """Test fallback a Gemini cuando MiniMax falla."""
        # MiniMax falla con error
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_minimax:
            mock_minimax.side_effect = Exception("Timeout")
            
            # Gemini responde correctamente
            with patch.object(router._gemini, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = MagicMock(
                    content="Hola desde Gemini",
                    tool_calls=[],
                    finish_reason="stop",
                    usage={}
                )
                
                response = await router.ainvoke(
                    messages=[{"role": "user", "content": "Hola"}]
                )
                
                assert "Gemini" in response.content
                assert response.provider == "gemini"
    
    @pytest.mark.asyncio
    async def test_fallback_on_empty_response(self, router):
        """Test fallback cuando el proveedor retorna respuesta vacía."""
        # MiniMax retorna respuesta vacía
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_minimax:
            mock_minimax.return_value = MagicMock(
                content="",
                tool_calls=[],
                finish_reason="stop",
                usage={}
            )
            
            # Gemini responde correctamente
            with patch.object(router._gemini, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = MagicMock(
                    content="Respuesta de Gemini",
                    tool_calls=[],
                    finish_reason="stop",
                    usage={}
                )
                
                response = await router.ainvoke(
                    messages=[{"role": "user", "content": "Hola"}]
                )
                
                assert "Gemini" in response.content
    
    @pytest.mark.asyncio
    async def test_fallback_on_503_error(self, router):
        """Test fallback en error 503."""
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_minimax:
            mock_minimax.side_effect = Exception("503 Service Unavailable")
            
            with patch.object(router._gemini, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.return_value = MagicMock(
                    content="Respuesta de respaldo",
                    tool_calls=[],
                    finish_reason="stop",
                    usage={}
                )
                
                response = await router.ainvoke(
                    messages=[{"role": "user", "content": "Hola"}]
                )
                
                assert "respaldo" in response.content
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(self, router):
        """Test cuando todos los proveedores fallan."""
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_minimax:
            mock_minimax.side_effect = Exception("Error")
            
            with patch.object(router._gemini, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.side_effect = Exception("Error")
                
                response = await router.ainvoke(
                    messages=[{"role": "user", "content": "Hola"}]
                )
                
                assert "problemas técnicos" in response.content
                assert response.provider == "fallback"
                assert response.error == "all_providers_failed"
    
    @pytest.mark.asyncio
    async def test_forced_provider(self, router):
        """Test forzar uso de un proveedor específico."""
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_minimax:
            mock_minimax.return_value = MagicMock(
                content="Respuesta forzada",
                tool_calls=[],
                finish_reason="stop",
                usage={}
            )
            
            response = await router.ainvoke(
                messages=[{"role": "user", "content": "Hola"}],
                forced_provider="minimax"
            )
            
            assert "forzada" in response.content
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff(self, router):
        """Test que hay reintentos con backoff exponencial."""
        router._max_retries = 2
        
        call_count = 0
        
        async def failing_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary error")
            return MagicMock(
                content="Éxito",
                tool_calls=[],
                finish_reason="stop",
                usage={}
            )
        
        with patch.object(router._minimax, "ainvoke", side_effect=failing_call):
            response = await router.ainvoke(
                messages=[{"role": "user", "content": "Hola"}]
            )
            
            assert call_count == 3  # 1 intento inicial + 2 reintentos
            assert "Éxito" in response.content
    
    @pytest.mark.asyncio
    async def test_provider_health_tracking(self, router):
        """Test que se marca proveedor como no saludable después de fallos."""
        assert router._provider_health["minimax"] is True
        assert router._provider_health["gemini"] is True
        
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_minimax:
            mock_minimax.side_effect = Exception("Error")
            
            with patch.object(router._gemini, "ainvoke", new_callable=AsyncMock) as mock_gemini:
                mock_gemini.side_effect = Exception("Error")
                
                await router.ainvoke(
                    messages=[{"role": "user", "content": "Hola"}]
                )
        
        assert router._provider_health["minimax"] is False
        assert router._provider_health["gemini"] is False
    
    @pytest.mark.asyncio
    async def test_reset_health(self, router):
        """Test reinicio de estados de salud."""
        router._provider_health["minimax"] = False
        router._provider_health["gemini"] = False
        
        router.reset_health()
        
        assert router._provider_health["minimax"] is True
        assert router._provider_health["gemini"] is True
    
    @pytest.mark.asyncio
    async def test_get_stats(self, router):
        """Test obtención de estadísticas."""
        router._request_count["minimax"] = 10
        router._request_count["gemini"] = 5
        
        stats = router.get_stats()
        
        assert stats["request_count"]["minimax"] == 10
        assert stats["request_count"]["gemini"] == 5
        assert "provider_health" in stats
    
    @pytest.mark.asyncio
    async def test_chat_simple(self, router):
        """Test de chat simple sin herramientas."""
        with patch.object(router._minimax, "ainvoke", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = MagicMock(
                content="¡Hola! Soy InmuebleBot",
                tool_calls=[],
                finish_reason="stop",
                usage={}
            )
            
            response = await router.chat(
                message="Hola",
                system_prompt="Eres un asistente"
            )
            
            assert "InmuebleBot" in response


class TestLLMResponse:
    """Tests para la clase LLMResponse."""
    
    def test_has_tool_calls(self):
        """Test propiedad has_tool_calls."""
        from app.agents.llm_router import ToolCall
        
        response = LLMResponse(
            content="Hola",
            tool_calls=[ToolCall("search", {})]
        )
        
        assert response.has_tool_calls is True
        
        response_empty = LLMResponse(content="Hola")
        assert response_empty.has_tool_calls is False
    
    def test_is_error(self):
        """Test propiedad is_error."""
        error_response = LLMResponse(content="Error", error="test_error")
        assert error_response.is_error is True
        
        empty_response = LLMResponse(content="")
        assert empty_response.is_error is True
        
        valid_response = LLMResponse(content="Hola")
        assert valid_response.is_error is False


class TestIntegration:
    """Tests de integración del router con el agente."""
    
    @pytest.mark.asyncio
    async def test_agent_uses_llm_router(self):
        """Test que el agente usa el router de LLMs."""
        from app.agents.real_estate_agent import RealEstateAgent
        
        with patch("app.agents.llm_router.LLMRouter"):
            agent = RealEstateAgent()
            
            assert hasattr(agent.llm, "ainvoke")


__all__ = [
    "TestLLMRouter",
    "TestLLMResponse",
    "TestIntegration",
]