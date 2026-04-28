"""
Tests para el servicio de handoff.
Ejecutar: pytest tests/test_handoff.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


class TestHandoffKeywords:
    """Tests para detección de palabras clave de handoff en el agente."""

    def test_detect_handoff_keyword_agente(self):
        """Test detección de 'hablar con un agente'."""
        from app.agents.real_estate_agent import RealEstateAgent
        
        agent = RealEstateAgent()
        
        assert agent._detect_handoff_request("Quiero hablar con un agente") is True
        assert agent._detect_handoff_request("Necesito hablar con un agente humano") is True

    def test_detect_handoff_keyword_persona(self):
        """Test detección de 'hablar con una persona'."""
        from app.agents.real_estate_agent import RealEstateAgent
        
        agent = RealEstateAgent()
        
        assert agent._detect_handoff_request("Quiero hablar con una persona") is True

    def test_detect_handoff_keyword_humano(self):
        """Test detección de 'hablar con un humano'."""
        from app.agents.real_estate_agent import RealEstateAgent
        
        agent = RealEstateAgent()
        
        assert agent._detect_handoff_request("Quiero hablar con un humano") is True

    def test_detect_handoff_keyword_pasame(self):
        """Test detección de 'pásame con'."""
        from app.agents.real_estate_agent import RealEstateAgent
        
        agent = RealEstateAgent()
        
        assert agent._detect_handoff_request("Pásame con un agente") is True

    def test_detect_handoff_keyword_negative(self):
        """Test que no detecta handoff en mensajes normales."""
        from app.agents.real_estate_agent import RealEstateAgent
        
        agent = RealEstateAgent()
        
        assert agent._detect_handoff_request("Busco una casa en Asunción") is False
        assert agent._detect_handoff_request("Quiero agendar una visita") is False
        assert agent._detect_handoff_request("Muéstrame propiedades") is False


class TestStateMachineHandoff:
    """Tests para verificar que el estado de handoff existe."""

    def test_human_assistance_state_exists(self):
        """Test que el estado HUMAN_ASSISTANCE existe."""
        from app.core.state_machine import ConversationStateEnum
        
        assert hasattr(ConversationStateEnum, 'HUMAN_ASSISTANCE')
        assert ConversationStateEnum.HUMAN_ASSISTANCE.value == "human_assistance"

    def test_handoff_transitions(self):
        """Test que las transiciones de handoff son válidas."""
        from app.core.state_machine import ConversationState, ConversationStateEnum
        
        state = ConversationState()
        
        assert state._is_valid_transition(
            ConversationStateEnum.SEARCHING.value,
            ConversationStateEnum.HUMAN_ASSISTANCE.value
        )
        
        assert state._is_valid_transition(
            ConversationStateEnum.QUALIFYING.value,
            ConversationStateEnum.HUMAN_ASSISTANCE.value
        )


class TestHandoffService:
    """Tests básicos del servicio de handoff."""

    def test_handoff_service_init(self):
        """Test que el servicio se inicializa sin errores."""
        from app.services.handoff_service import HandoffService
        
        service = HandoffService()
        assert service is not None


class TestAdminAuth:
    """Tests para autenticación de admin."""

    def test_admin_api_key_in_config(self):
        """Test que ADMIN_API_KEY está configurado."""
        from app.core.config import get_settings
        
        settings = get_settings()
        assert hasattr(settings, 'ADMIN_API_KEY')
        assert settings.ADMIN_API_KEY is not None


class TestHandoffToolDefinition:
    """Tests para verificar que request_human_assistance está en tools."""

    def test_handoff_tool_in_prompts(self):
        """Test que la herramienta de handoff está definida en prompts."""
        from app.agents.prompts import TOOL_DEFINITIONS
        
        tool_names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert "request_human_assistance" in tool_names

    def test_handoff_tool_in_functions(self):
        """Test que la función de handoff está en TOOL_FUNCTIONS."""
        from app.agents.tools import TOOL_FUNCTIONS
        
        assert "request_human_assistance" in TOOL_FUNCTIONS

    def test_handoff_tool_definition_has_description(self):
        """Test que la herramienta de handoff tiene descripción."""
        from app.agents.prompts import TOOL_DEFINITIONS
        
        handoff_tool = next(
            (t for t in TOOL_DEFINITIONS if t["function"]["name"] == "request_human_assistance"),
            None
        )
        assert handoff_tool is not None
        assert "description" in handoff_tool["function"]
        assert "humano" in handoff_tool["function"]["description"].lower()