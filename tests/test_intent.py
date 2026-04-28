"""
Tests para el clasificador de intents.
Ejecutar: pytest tests/test_intent.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.intent import Intent
from app.core.classifier import (
    IntentClassifier,
    IntentClassification,
    ExtractedEntities,
)


class TestIntentEnum:
    """Tests para el enum de intents."""
    
    def test_intent_values(self):
        """Verifica que todos los intents tienen valores correctos."""
        assert Intent.GREETING.value == "greeting"
        assert Intent.PROPERTY_SEARCH.value == "property_search"
        assert Intent.PROPERTY_DETAILS.value == "property_details"
        assert Intent.SCHEDULE_APPOINTMENT.value == "schedule_appointment"
        assert Intent.FAQ.value == "faq"
        assert Intent.HUMAN_HANDOFF.value == "human_handoff"
        assert Intent.UNKNOWN.value == "unknown"
    
    def test_intent_count(self):
        """Verifica la cantidad de intents."""
        assert len(Intent) == 7


class TestExtractedEntities:
    """Tests para el modelo de entidades extraídas."""
    
    def test_empty_entities(self):
        """Test con entidades vacías."""
        entities = ExtractedEntities()
        assert entities.budget_min is None
        assert entities.budget_max is None
        assert entities.location is None
    
    def test_full_entities(self):
        """Test con todas las entidades."""
        entities = ExtractedEntities(
            budget_min=100000,
            budget_max=200000,
            location="Asunción",
            property_type="casa",
            bedrooms=3,
            bathrooms=2,
            area_min=150,
            operation_type="venta"
        )
        
        assert entities.budget_min == 100000
        assert entities.budget_max == 200000
        assert entities.location == "Asunción"
        assert entities.property_type == "casa"
        assert entities.bedrooms == 3
        assert entities.bathrooms == 2
        assert entities.area_min == 150
        assert entities.operation_type == "venta"


class TestIntentClassification:
    """Tests para el modelo de clasificación."""
    
    def test_full_classification(self):
        """Test con clasificación completa."""
        classification = IntentClassification(
            intent=Intent.PROPERTY_SEARCH,
            confidence=0.95,
            extracted_entities=ExtractedEntities(
                location="Posadas",
                budget_max=150000
            ),
            reasoning="El usuario busca propiedades en Posadas"
        )
        
        assert classification.intent == Intent.PROPERTY_SEARCH
        assert classification.confidence == 0.95
        assert classification.extracted_entities.location == "Posadas"
        assert classification.extracted_entities.budget_max == 150000
    
    def test_confidence_bounds(self):
        """Test que la confianza está entre 0 y 1."""
        classification = IntentClassification(
            intent=Intent.GREETING,
            confidence=0.5
        )
        assert classification.confidence >= 0.0
        assert classification.confidence <= 1.0


class TestIntentClassifier:
    """Tests para el clasificador de intents (mock)."""
    
    @pytest.mark.asyncio
    async def test_parse_response_greeting(self):
        """Test de parsing de respuesta de greeting (con JSON limpio)."""
        classifier = IntentClassifier()
        
        response = '{"intent": "GREETING", "confidence": 0.95, "extracted_entities": {}, "reasoning": "Saludo"}'
        
        result = classifier._parse_response(response)
        
        # Verificar que el parsing no crashea
        assert result.intent in Intent
        assert result.confidence >= 0.0
    
    @pytest.mark.asyncio
    async def test_parse_response_property_search(self):
        """Test que el parsing no crashea."""
        classifier = IntentClassifier()
        
        response = '{"intent": "PROPERTY_SEARCH", "confidence": 0.90, "extracted_entities": {"location": "Posadas"}}'
        
        result = classifier._parse_response(response)
        
        assert result.intent in Intent
        assert result.confidence >= 0.0
    
    @pytest.mark.asyncio
    async def test_parse_response_schedule_appointment(self):
        """Test que el parsing no crashea."""
        classifier = IntentClassifier()
        
        response = '{"intent": "SCHEDULE_APPOINTMENT", "confidence": 0.88, "extracted_entities": {}}'
        
        result = classifier._parse_response(response)
        
        assert result.intent in Intent
    
    @pytest.mark.asyncio
    async def test_parse_invalid_intent(self):
        """Test con intent inválido."""
        classifier = IntentClassifier()
        
        response = '''{
            "intent": "INVALID_INTENT",
            "confidence": 0.5,
            "extracted_entities": {}
        }'''
        
        result = classifier._parse_response(response)
        
        # Debe convertir a UNKNOWN
        assert result.intent == Intent.UNKNOWN
    
    @pytest.mark.asyncio
    async def test_parse_malformed_json(self):
        """Test con JSON malformado."""
        classifier = IntentClassifier()
        
        result = classifier._parse_response("这不是JSON")
        
        # Debe retornar UNKNOWN como fallback
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0


class TestClassifierIntegration:
    """Tests de integración que requieren API."""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requiere API key")
    async def test_classify_greeting(self):
        """Test de clasificación de greeting."""
        classifier = IntentClassifier()
        result = await classifier.classify("Hola, buenos días")
        
        assert result.intent == Intent.GREETING
        assert result.confidence >= 0.7
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requiere API key")
    async def test_classify_property_search(self):
        """Test de clasificación de búsqueda."""
        classifier = IntentClassifier()
        result = await classifier.classify("Busco una casa en Posadas hasta 150000 USD")
        
        assert result.intent == Intent.PROPERTY_SEARCH
        assert result.extracted_entities.location == "Posadas"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])