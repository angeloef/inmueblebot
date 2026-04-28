"""
Tests para el router.
Ejecutar: pytest tests/test_router.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.router import Router
from app.core.intent import Intent
from app.core.classifier import IntentClassification, ExtractedEntities
from app.core.state_machine import ConversationStateEnum


class TestRouter:
    """Tests para el Router."""
    
    @pytest.fixture
    def router(self):
        """Fixture que retorna un router con mocks."""
        return Router()
    
    @pytest.mark.asyncio
    async def test_process_greeting(self, router):
        """Test de procesamiento de greeting."""
        with patch.object(router.classifier, "classify", new_callable=AsyncMock) as mock_classify, \
             patch.object(router.state, "set_state", new_callable=AsyncMock) as mock_set_state, \
             patch.object(router.memory, "save_message", new_callable=AsyncMock), \
             patch.object(router.memory, "get_user_context", new_callable=AsyncMock) as mock_context, \
             patch.object(router.state, "get_state", new_callable=AsyncMock):
            
            # Mock clasificación
            mock_classify.return_value = IntentClassification(
                intent=Intent.GREETING,
                confidence=0.95
            )
            
            # Mock contexto y estado
            mock_context.return_value = {"current_state": "idle"}
            mock_set_state.return_value = True
            
            result = await router.process_message(
                phone="+595981234567",
                message_text="Hola, buenos días"
            )
            
            assert result["intent"] == Intent.GREETING.value
            assert result["next_state"] == ConversationStateEnum.QUALIFYING.value
            assert "bienvenido" in result["response_text"].lower()
    
    @pytest.mark.asyncio
    async def test_process_property_search(self, router):
        """Test de procesamiento de búsqueda de propiedades."""
        with patch.object(router.classifier, "classify", new_callable=AsyncMock) as mock_classify, \
             patch.object(router.state, "set_state", new_callable=AsyncMock) as mock_set_state, \
             patch.object(router.memory, "save_message", new_callable=AsyncMock), \
             patch.object(router.memory, "get_user_context", new_callable=AsyncMock) as mock_context, \
             patch.object(router.state, "get_state", new_callable=AsyncMock), \
             patch("app.services.property_service.property_service") as mock_prop_svc:
            
            mock_classify.return_value = IntentClassification(
                intent=Intent.PROPERTY_SEARCH,
                confidence=0.90,
                extracted_entities=ExtractedEntities(
                    location="Posadas",
                    budget_max=150000,
                    bedrooms=2,
                    property_type="casa"
                )
            )
            
            mock_prop_svc.search_properties = AsyncMock(return_value=[
                {"id": 1, "title": "Casa en Posadas", "price": 120000, "location": "Posadas", "bedrooms": 2}
            ])
            
            mock_context.return_value = {"current_state": "idle"}
            mock_set_state.return_value = True
            
            result = await router.process_message(
                phone="+595981234567",
                message_text="Busco una casa en Posadas de 2 dormitorios hasta 150000 USD"
            )
            
            assert result["intent"] == Intent.PROPERTY_SEARCH.value
            assert result["next_state"] == ConversationStateEnum.SEARCHING.value
            assert "search_results" in result["rich_content"].get("action", "")
    
    @pytest.mark.asyncio
    async def test_process_schedule_appointment(self, router):
        """Test de procesamiento de agendamiento."""
        with patch.object(router.classifier, "classify", new_callable=AsyncMock) as mock_classify, \
             patch.object(router.state, "set_state", new_callable=AsyncMock) as mock_set_state, \
             patch.object(router.memory, "save_message", new_callable=AsyncMock), \
             patch.object(router.memory, "get_user_context", new_callable=AsyncMock) as mock_context, \
             patch.object(router.state, "get_state", new_callable=AsyncMock):
            
            mock_classify.return_value = IntentClassification(
                intent=Intent.SCHEDULE_APPOINTMENT,
                confidence=0.88
            )
            
            mock_context.return_value = {"current_state": "viewing_property"}
            mock_set_state.return_value = True
            
            result = await router.process_message(
                phone="+595981234567",
                message_text="Quiero agendar una visita"
            )
            
            assert result["intent"] == Intent.SCHEDULE_APPOINTMENT.value
            assert result["next_state"] == ConversationStateEnum.BOOKING.value
    
    @pytest.mark.asyncio
    async def test_process_human_handoff(self, router):
        """Test de escalamiento a agente humano."""
        with patch.object(router.classifier, "classify", new_callable=AsyncMock) as mock_classify, \
             patch.object(router.state, "set_state", new_callable=AsyncMock) as mock_set_state, \
             patch.object(router.memory, "save_message", new_callable=AsyncMock), \
             patch.object(router.memory, "get_user_context", new_callable=AsyncMock) as mock_context, \
             patch.object(router.state, "get_state", new_callable=AsyncMock):
            
            mock_classify.return_value = IntentClassification(
                intent=Intent.HUMAN_HANDOFF,
                confidence=0.95
            )
            
            mock_context.return_value = {"current_state": "searching"}
            mock_set_state.return_value = True
            
            result = await router.process_message(
                phone="+595981234567",
                message_text="Quiero hablar con un agente humano"
            )
            
            assert result["intent"] == Intent.HUMAN_HANDOFF.value
            assert result["next_state"] == ConversationStateEnum.HUMAN_ASSISTANCE.value
            assert result["rich_content"]["action"] == "handoff_initiated"
    
    @pytest.mark.asyncio
    async def test_process_unknown_intent(self, router):
        """Test de mensaje no entendido."""
        with patch.object(router.classifier, "classify", new_callable=AsyncMock) as mock_classify, \
             patch.object(router.memory, "save_message", new_callable=AsyncMock), \
             patch.object(router.memory, "get_user_context", new_callable=AsyncMock) as mock_context, \
             patch.object(router.state, "get_state", new_callable=AsyncMock):
            
            mock_classify.return_value = IntentClassification(
                intent=Intent.UNKNOWN,
                confidence=0.0
            )
            
            mock_context.return_value = {"current_state": "qualifying"}
            
            result = await router.process_message(
                phone="+595981234567",
                message_text="xyzabc123"
            )
            
            assert result["intent"] == Intent.UNKNOWN.value
            assert "no entiendo" in result["response_text"].lower()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, router):
        """Test de manejo de errores."""
        with patch.object(router.classifier, "classify", new_callable=AsyncMock) as mock_classify:
            # Simular error
            mock_classify.side_effect = Exception("Error simulado")
            
            result = await router.process_message(
                phone="+595981234567",
                message_text="Test message"
            )
            
            assert result["intent"] == Intent.UNKNOWN.value
            assert "problema" in result["response_text"].lower()


class TestRouterBuildSearch:
    """Tests para los métodos辅助 del router."""
    
    @pytest.fixture
    def router(self):
        return Router()
    
    def test_build_search_message_full(self, router):
        """Test de construcción de mensaje de búsqueda."""
        entities = ExtractedEntities(
            location="Posadas",
            budget_max=150000,
            bedrooms=2,
            property_type="casa",
            operation_type="venta"
        )
        
        msg = router._build_search_message(entities)
        
        assert "casa" in msg
        assert "Posadas" in msg
        assert "venta" in msg
    
    def test_build_search_message_minimal(self, router):
        """Test con entidades mínimas."""
        entities = ExtractedEntities(
            location="Asunción"
        )
        
        msg = router._build_search_message(entities)
        
        assert "Asunción" in msg
    
    def test_format_search_criteria(self, router):
        """Test de formateo de criterios."""
        entities = ExtractedEntities(
            location="Encarnación",
            budget_max=200000,
            property_type="departamento"
        )
        
        criteria = router._format_search_criteria(entities)
        
        assert "ubicación: Encarnación" in criteria
        assert "presupuesto: hasta $200,000 USD" in criteria
        assert "tipo: departamento" in criteria


if __name__ == "__main__":
    pytest.main([__file__, "-v"])