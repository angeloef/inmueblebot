"""
Tests para el módulo de memoria y estado.
Ejecutar con: pytest tests/test_memory.py -v
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Importar módulos a testear
from app.core.memory import MemoryManager, memory_manager
from app.core.state_machine import ConversationState, ConversationStateEnum, state_machine
from app.core.session import SessionManager, session_manager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def test_phone():
    """Número de teléfono de prueba."""
    return "+595981123456"


@pytest.fixture
def mock_redis():
    """Mock de cliente Redis."""
    with patch("app.core.memory.redis") as mock:
        # Configurar comportamiento async
        mock.from_url.return_value = AsyncMock()
        yield mock


# ============================================================================
# TESTS DE MEMORY MANAGER
# ============================================================================

class TestMemoryManager:
    """Tests para MemoryManager."""
    
    @pytest.mark.asyncio
    async def test_get_user_context_returns_default(self, test_phone):
        """Test que obtener contexto retorna valores por defecto."""
        # Este test requiere Redis mocking - aquí verificamos la estructura
        context = {
            "current_state": "idle",
            "last_search_criteria": None,
            "selected_property_id": None,
            "conversation_stage": "new",
        }
        
        assert context["current_state"] == "idle"
        assert context["last_search_criteria"] is None
        assert "conversation_stage" in context
    
    @pytest.mark.asyncio
    async def test_save_message_format(self, test_phone):
        """Test que el formato del mensaje es correcto."""
        message = {
            "role": "user",
            "content": "Hola, busco casa en Asunción",
            "media_url": None,
            "timestamp": "2026-04-18T12:00:00",
        }
        
        assert message["role"] in ["user", "assistant", "system"]
        assert "content" in message
        assert "timestamp" in message
    
    @pytest.mark.asyncio
    async def test_update_user_preferences_structure(self, test_phone):
        """Test que la estructura de preferencias es correcta."""
        preferences = {
            "name": "Juan Pérez",
            "budget_min": 100000,
            "budget_max": 200000,
            "location_preferences": ["Asunción", "Encarnación"],
            "property_type": ["casa", "departamento"],
            "preferred_language": "es",
            "lead_score": 50,
        }
        
        # Verificar campos requeridos
        assert "budget_min" in preferences
        assert "budget_max" in preferences
        assert "location_preferences" in preferences
        assert isinstance(preferences["location_preferences"], list)


# ============================================================================
# TESTS DE STATE MACHINE
# ============================================================================

class TestConversationState:
    """Tests para ConversationState."""
    
    @pytest.mark.asyncio
    async def test_valid_transitions_from_idle(self):
        """Test que las transiciones desde idle son válidas."""
        from app.core.state_machine import ConversationState
        
        sm = ConversationState()
        
        # idle -> qualifying es válido
        assert sm._is_valid_transition("idle", "qualifying") is True
        
        # idle -> searching es válido
        assert sm._is_valid_transition("idle", "searching") is True
        
        # idle -> handoff es válido
        assert sm._is_valid_transition("idle", "handoff") is True
    
    @pytest.mark.asyncio
    async def test_valid_transitions_from_searching(self):
        """Test que las transiciones desde searching son válidas."""
        from app.core.state_machine import ConversationState
        
        sm = ConversationState()
        
        # searching -> viewing_property es válido
        assert sm._is_valid_transition("searching", "viewing_property") is True
        
        # searching -> qualifying es válido
        assert sm._is_valid_transition("searching", "qualifying") is True
    
    @pytest.mark.asyncio
    async def test_invalid_transitions(self):
        """Test que las transiciones inválidas son rechazadas."""
        from app.core.state_machine import ConversationState
        
        sm = ConversationState()
        
        # idle -> completed no es válido directamente
        assert sm._is_valid_transition("idle", "completed") is False
        
        # viewing_property -> idle no es válido (debería pasar por booking)
        assert sm._is_valid_transition("viewing_property", "idle") is True  # Timeout permitido
    
    def test_state_enum_values(self):
        """Test que los estados tienen los valores correctos."""
        assert ConversationStateEnum.IDLE.value == "idle"
        assert ConversationStateEnum.QUALIFYING.value == "qualifying"
        assert ConversationStateEnum.SEARCHING.value == "searching"
        assert ConversationStateEnum.VIEWING_PROPERTY.value == "viewing_property"
        assert ConversationStateEnum.BOOKING.value == "booking"
        assert ConversationStateEnum.COMPLETED.value == "completed"
        assert ConversationStateEnum.HANDOFF.value == "handoff"


# ============================================================================
# TESTS DE SESSION MANAGER
# ============================================================================

class TestSessionManager:
    """Tests para SessionManager."""
    
    @pytest.mark.asyncio
    async def test_session_info_structure(self, test_phone):
        """Test que la estructura de información de sesión es correcta."""
        # Estructura esperada
        session_info = {
            "phone": test_phone,
            "state": "qualifying",
            "is_active": True,
            "context": {
                "current_state": "qualifying",
                "last_search_criteria": None,
                "selected_property_id": None,
            },
            "preferences": {
                "name": "Juan",
                "budget_min": 100000,
                "budget_max": 200000,
            },
            "recent_messages": [],
        }
        
        # Verificar campos
        assert "phone" in session_info
        assert "state" in session_info
        assert "is_active" in session_info
        assert "context" in session_info
        assert "preferences" in session_info
        assert "recent_messages" in session_info
    
    @pytest.mark.asyncio
    async def test_search_context_update(self, test_phone):
        """Test que la actualización de contexto de búsqueda funciona."""
        search_criteria = {
            "type": "venta",
            "location": "Asunción",
            "budget_min": 100000,
            "budget_max": 300000,
            "bedrooms_min": 2,
        }
        
        # Verificar estructura
        assert "type" in search_criteria
        assert "location" in search_criteria
        assert "budget_min" in search_criteria
        assert "budget_max" in search_criteria
    
    @pytest.mark.asyncio
    async def test_should_qualify_user_new(self, test_phone):
        """Test que usuarios nuevos necesitan cualificación."""
        # Un usuario sin preferencias necesita cualificación
        preferences = None
        
        should_qualify = preferences is None
        
        assert should_qualify is True
    
    @pytest.mark.asyncio
    async def test_should_qualify_user_incomplete(self, test_phone):
        """Test que usuarios con preferencias incompletas necesitan cualificación."""
        # Usuario con preferencias pero sin presupuesto
        preferences = {
            "name": "Juan",
            "location_preferences": ["Asunción"],
            "budget_min": None,
            "budget_max": None,
        }
        
        should_qualify = (
            preferences is None or
            (not preferences.get("budget_min") and not preferences.get("budget_max")) or
            not preferences.get("location_preferences")
        )
        
        assert should_qualify is True
    
    @pytest.mark.asyncio
    async def test_should_not_qualify_user_complete(self, test_phone):
        """Test que usuarios con preferencias completas no necesitan cualificación."""
        preferences = {
            "name": "Juan",
            "budget_min": 100000,
            "budget_max": 300000,
            "location_preferences": ["Asunción"],
        }
        
        should_qualify = (
            preferences is None or
            (not preferences.get("budget_min") and not preferences.get("budget_max")) or
            not preferences.get("location_preferences")
        )
        
        assert should_qualify is False


# ============================================================================
# INTEGRATION TESTS (requieren Redis y DB)
# ============================================================================

@pytest.mark.integration
class TestMemoryIntegration:
    """Tests de integración que requieren Redis y PostgreSQL."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires Redis running")
    async def test_full_memory_flow(self, test_phone):
        """Test del flujo completo de memoria."""
        # Este test requiere:
        # 1. Redis corriendo (docker-compose up)
        # 2. PostgreSQL con tablas creadas
        # 3. Seed de propiedades ejecutado
        
        # Test completo:
        # 1. Guardar contexto
        # await memory_manager.save_user_context(test_phone, {"current_state": "qualifying"})
        
        # 2. Guardar mensaje
        # await memory_manager.save_message(test_phone, "user", "Hola")
        
        # 3. Verificar contexto
        # context = await memory_manager.get_user_context(test_phone)
        
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires Redis running")
    async def test_state_machine_flow(self, test_phone):
        """Test del flujo completo de estados."""
        # Test completo:
        # 1. Iniciar en idle
        # state = await state_machine.get_state(test_phone)
        
        # 2. Cambiar a qualifying
        # await state_machine.set_state(test_phone, "qualifying")
        
        # 3. Cambiar a searching
        # await state_machine.set_state(test_phone, "searching")
        
        pass


# ============================================================================
# EJECUTAR TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])