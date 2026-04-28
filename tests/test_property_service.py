"""
Tests para el servicio de propiedades.
Ejecutar: pytest tests/test_property_service.py -v
"""
import pytest
from uuid import uuid4

from app.services.property_service import PropertyService
from app.db.models import Property


class TestPropertyService:
    """Tests para PropertyService."""
    
    @pytest.fixture
    def service(self):
        """Fixture que retorna el servicio."""
        return PropertyService()
    
    @pytest.mark.asyncio
    async def test_search_all_properties(self, service):
        """Test de búsqueda sin criterios."""
        results = await service.search_properties({})
        
        assert isinstance(results, list)
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_search_by_location(self, service):
        """Test de búsqueda por ubicación."""
        results = await service.search_properties({"location": "Asunción"})
        
        assert isinstance(results, list)
        for prop in results:
            assert "asunción" in prop.location.lower() or "asuncion" in prop.location.lower()
    
    @pytest.mark.asyncio
    async def test_search_by_budget(self, service):
        """Test de búsqueda por presupuesto."""
        results = await service.search_properties({"budget_max": 100000})
        
        assert isinstance(results, list)
        for prop in results:
            assert prop.price <= 100000
    
    @pytest.mark.asyncio
    async def test_search_by_operation_type(self, service):
        """Test de búsqueda por tipo de operación."""
        # Buscar propiedades en venta
        results = await service.search_properties({"operation_type": "venta"})
        
        assert isinstance(results, list)
        for prop in results:
            assert prop.type == "venta"
    
    @pytest.mark.asyncio
    async def test_search_by_bedrooms(self, service):
        """Test de búsqueda por número de dormitorios."""
        results = await service.search_properties({"bedrooms": 3})
        
        assert isinstance(results, list)
        # El repositorio filtra por bedrooms_min, así que puede tener más
        for prop in results:
            assert prop.bedrooms is None or prop.bedrooms >= 3
    
    @pytest.mark.asyncio
    async def test_search_with_multiple_criteria(self, service):
        """Test de búsqueda con múltiples criterios."""
        results = await service.search_properties({
            "location": "Asunción",
            "budget_max": 200000,
            "bedrooms": 2,
            "limit": 5
        })
        
        assert isinstance(results, list)
        assert len(results) <= 5
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, service):
        """Test de búsqueda sin resultados."""
        results = await service.search_properties({"budget_max": 1})  # Muy bajo
        
        assert isinstance(results, list)
        # Puede retornar lista vacía o no encontrar
    
    @pytest.mark.asyncio
    async def test_get_random_properties(self, service):
        """Test de obtener propiedades aleatorias."""
        results = await service.get_random_properties(limit=3)
        
        assert isinstance(results, list)
        assert len(results) <= 3
    
    @pytest.mark.asyncio
    async def test_get_properties_by_location(self, service):
        """Test de búsqueda por ubicación."""
        results = await service.get_properties_by_location("Encarnación")
        
        assert isinstance(results, list)
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_get_featured_properties(self, service):
        """Test de obtener propiedades destacadas."""
        results = await service.get_featured_properties(limit=5)
        
        assert isinstance(results, list)
        assert len(results) <= 5


class TestPropertyFormatting:
    """Tests para el formateo de propiedades."""
    
    def test_format_property_list_empty(self):
        """Test formateo con lista vacía."""
        from app.agents.tools import format_property_list
        
        result = format_property_list([])
        
        assert "No encontré" in result
        assert "propiedades" in result.lower()
    
    def test_format_property_list_with_data(self):
        """Test formateo con propiedades."""
        from app.agents.tools import format_property_list
        from unittest.mock import MagicMock
        
        # Crear propiedades mock
        prop1 = MagicMock()
        prop1.id = uuid4()
        prop1.title = "Casa en Posadas"
        prop1.price = 150000
        prop1.type = "venta"
        prop1.location = "Posadas"
        prop1.bedrooms = 3
        prop1.bathrooms = 2
        prop1.area_m2 = 200
        prop1.images = []
        
        prop2 = MagicMock()
        prop2.id = uuid4()
        prop2.title = "Departamento en Asunción"
        prop2.price = 95000
        prop2.type = "venta"
        prop2.location = "Asunción"
        prop2.bedrooms = 2
        prop2.bathrooms = 1
        prop2.area_m2 = 85
        prop2.images = []
        
        result = format_property_list([prop1, prop2])
        
        assert "Encontré" in result
        assert "Casa en Posadas" in result
        assert "Departamento en Asunción" in result
        assert "$150,000" in result or "150,000" in result
    
    def test_format_property_details_none(self):
        """Test formateo de detalles con propiedad nula."""
        from app.agents.tools import format_property_details
        
        result = format_property_details(None)
        
        assert "No encontré" in result
    
    def test_format_property_details_with_data(self):
        """Test formateo de detalles con propiedad."""
        from app.agents.tools import format_property_details
        from unittest.mock import MagicMock
        
        prop = MagicMock()
        prop.id = uuid4()
        prop.title = "Casa moderna"
        prop.price = 180000
        prop.type = "venta"
        prop.description = "Hermosa casa con piscina"
        prop.location = "Villa Edna, Asunción"
        prop.bedrooms = 3
        prop.bathrooms = 2
        prop.area_m2 = 250
        prop.property_type = "casa"
        prop.images = ["http://example.com/img.jpg"]
        
        result = format_property_details(prop)
        
        assert "Casa moderna" in result
        assert "Villa Edna" in result
        assert "180,000" in result


class TestSearchCriteria:
    """Tests para construir criterios de búsqueda."""
    
    def test_build_criteria_minimal(self):
        """Test construir criterios mínimos."""
        from app.core.classifier import ExtractedEntities
        
        entities = ExtractedEntities()
        
        # El test debería verificar el método en el router
        # Aquí verificamos que las entidades funcionan
        assert entities.location is None
        assert entities.budget_max is None
    
    def test_build_criteria_full(self):
        """Test construir criterios completos."""
        from app.core.classifier import ExtractedEntities
        
        entities = ExtractedEntities(
            location="Posadas",
            budget_max=150000,
            budget_min=50000,
            bedrooms=2,
            bathrooms=1,
            property_type="casa",
            operation_type="venta"
        )
        
        assert entities.location == "Posadas"
        assert entities.budget_max == 150000
        assert entities.budget_min == 50000
        assert entities.bedrooms == 2
        assert entities.bathrooms == 1
        assert entities.property_type == "casa"
        assert entities.operation_type == "venta"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])