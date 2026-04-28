"""
Tests para el agente de bienes raíces.
Ejecutar: pytest tests/test_agent.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.agents.real_estate_agent import RealEstateAgent
from app.agents.llm import AsyncMiniMaxClient
from app.agents.llm_router import LLMResponse, ToolCall
from app.agents.tools import execute_tool, search_properties, get_property_details
from app.core.intent import Intent


class TestAsyncMiniMaxClient:
    """Tests para el cliente LLM."""
    
    @pytest.mark.asyncio
    async def test_ainvoke_without_api_key(self):
        """Test cuando no hay API key configurada."""
        client = AsyncMiniMaxClient()
        client._api_key = None
        
        response = await client.ainvoke(
            messages=[{"role": "user", "content": "Hola"}]
        )
        
        assert "no está disponible" in response.content.lower()
    
    @pytest.mark.asyncio
    async def test_parse_response_without_tool_calls(self):
        """Test parseo de respuesta sin tool calls."""
        client = AsyncMiniMaxClient()
        
        data = {
            "choices": [{
                "message": {"content": "Hola, ¿en qué puedo ayudarte?"},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}
        }
        
        response = client._parse_response(data)
        
        assert response.content == "Hola, ¿en qué puedo ayudarte?"
        assert not response.has_tool_calls
        assert response.finish_reason == "stop"
    
    @pytest.mark.asyncio
    async def test_parse_response_with_tool_calls(self):
        """Test parseo de respuesta con tool calls."""
        client = AsyncMiniMaxClient()
        
        data = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_properties",
                                "arguments": '{"location": "Asunción", "budget_max": 100000}'
                            }
                        }
                    ]
                },
                "finish_reason": "tool_calls"
            }]
        }
        
        response = client._parse_response(data)
        
        assert response.has_tool_calls
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search_properties"
        assert response.tool_calls[0].arguments["location"] == "Asunción"


class TestTools:
    """Tests para las herramientas del agente."""
    
    @pytest.mark.asyncio
    async def test_execute_search_properties(self):
        """Test de búsqueda de propiedades con mock."""
        with patch("app.agents.tools.property_service") as mock_prop_svc:
            mock_prop_svc.search_properties = AsyncMock(return_value=[])
            
            result = await execute_tool(
                tool_name="search_properties",
                arguments={"location": "Asunción", "budget_max": 100000}
            )
            
            assert "No encontré propiedades" in result
            mock_prop_svc.search_properties.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_get_property_details(self):
        """Test de obtención de detalles con mock."""
        with patch("app.agents.tools.property_service") as mock_prop_svc:
            mock_prop = MagicMock()
            mock_prop.id = uuid4()
            mock_prop.title = "Casa de prueba"
            mock_prop.price = 150000
            mock_prop.type = "venta"
            mock_prop.location = "Asunción"
            mock_prop.bedrooms = 3
            mock_prop.bathrooms = 2
            mock_prop.area_m2 = 200
            mock_prop.description = "Casa hermosa"
            mock_prop.images = []
            
            mock_prop_svc.get_property_details = AsyncMock(return_value=mock_prop)
            mock_prop_svc.get_property_by_id = AsyncMock(return_value=mock_prop)
            
            result = await execute_tool(
                tool_name="get_property_details",
                arguments={"property_id": str(mock_prop.id)}
            )
            
            assert "Casa de prueba" in result
            assert "150,000" in result
    
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test de herramienta desconocida."""
        result = await execute_tool(
            tool_name="unknown_tool",
            arguments={}
        )
        
        assert "no encontrada" in result.lower()


class TestRealEstateAgent:
    """Tests para el agente RealEstateAgent."""
    
    @pytest.fixture
    def agent(self):
        """Fixture que retorna un agente con mocks."""
        with patch("app.agents.real_estate_agent.llm_router"):
            return RealEstateAgent()
    
    @pytest.mark.asyncio
    async def test_process_turn_greeting(self, agent):
        """Test de procesamiento de greeting sin tool calling."""
        with patch.object(agent.llm, "ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = LLMResponse(
                content="¡Hola! ¿En qué puedo ayudarte?",
                finish_reason="stop"
            )
            
            with patch("app.agents.real_estate_agent.memory_manager") as mock_memory:
                mock_memory.get_user_context = AsyncMock(return_value={
                    "current_state": "idle",
                    "preferences": {},
                    "recent_messages": []
                })
                mock_memory.save_message = AsyncMock()
                
                with patch("app.agents.real_estate_agent.state_machine") as mock_state:
                    mock_state.set_state = AsyncMock()
                    
                    result = await agent.process_turn(
                        phone="+595981234567",
                        user_message="Hola",
                        intent=Intent.GREETING
                    )
                    
                    assert "response_text" in result
                    assert "tools_used" in result
                    assert result["tools_used"] == []
    
    @pytest.mark.asyncio
    async def test_process_turn_property_search(self, agent):
        """Test de búsqueda de propiedades con tool calling."""
        with patch.object(agent.llm, "ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="search_properties",
                        arguments={"location": "Asunción", "budget_max": 100000}
                    )],
                    finish_reason="tool_calls"
                ),
                LLMResponse(
                    content="Encontré propiedades en Asunción...",
                    finish_reason="stop"
                )
            ]
            
            with patch("app.agents.real_estate_agent.memory_manager") as mock_memory:
                mock_memory.get_user_context = AsyncMock(return_value={
                    "current_state": "idle",
                    "preferences": {},
                    "recent_messages": []
                })
                mock_memory.save_message = AsyncMock()
                mock_memory.update_user_preferences = AsyncMock()
                
                with patch("app.agents.real_estate_agent.state_machine") as mock_state:
                    mock_state.set_state = AsyncMock()
                    
                    with patch("app.agents.tools.property_service") as mock_prop:
                        mock_prop.search_properties = AsyncMock(return_value=[])
                        
                        result = await agent.process_turn(
                            phone="+595981234567",
                            user_message="Busco casa en Asunción hasta 100mil",
                            intent=Intent.PROPERTY_SEARCH
                        )
                        
                        assert "search_properties" in result["tools_used"]
    
    @pytest.mark.asyncio
    async def test_process_turn_error_handling(self, agent):
        """Test de manejo de errores."""
        with patch.object(agent.llm, "ainvoke", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("Error de prueba")
            
            result = await agent.process_turn(
                phone="+595981234567",
                user_message="Test",
                intent=Intent.PROPERTY_SEARCH
            )
            
            assert "problema" in result["response_text"].lower()
            assert result["tools_used"] == []


class TestAgentIntegration:
    """Tests de integración del agente."""
    
    @pytest.mark.asyncio
    async def test_full_conversation_flow(self):
        """Test del flujo completo de conversación."""
        with patch("app.agents.real_estate_agent.llm_router") as MockRouter:
            agent = RealEstateAgent()
            
            mock_client = MagicMock()
            MockRouter.return_value = mock_client
            
            mock_client.ainvoke = AsyncMock(return_value=LLMResponse(
                content="¿Buscas propiedades en Asunción?",
                finish_reason="stop"
            ))
            
            with patch("app.agents.real_estate_agent.memory_manager") as mock_memory:
                mock_memory.get_user_context = AsyncMock(return_value={
                    "current_state": "idle",
                    "preferences": {"location": "Asunción"},
                    "recent_messages": []
                })
                mock_memory.save_message = AsyncMock()
                mock_memory.update_user_preferences = AsyncMock()
                
                with patch("app.agents.real_estate_agent.state_machine") as mock_state:
                    mock_state.set_state = AsyncMock()
                    
                    result = await agent.process_turn(
                        phone="+595981234567",
                        user_message="Hola, estoy buscando casa"
                    )
                    
                    assert "response_text" in result


__all__ = [
    "TestAsyncMiniMaxClient",
    "TestTools", 
    "TestRealEstateAgent",
    "TestAgentIntegration",
]