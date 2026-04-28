"""
Tests para el servicio de citas/appointments.
Ejecutar: pytest tests/test_appointment_service.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock

from app.services.appointment_service import (
    format_appointment_confirmation,
    format_appointment_list
)


class TestFormattingFunctions:
    """Tests para funciones de formateo."""
    
    def test_format_appointment_confirmation(self):
        """Test de formateo de confirmación."""
        mock_appointment = MagicMock()
        mock_appointment.id = uuid4()
        mock_appointment.start_time = datetime(2026, 4, 25, 15, 0, tzinfo=timezone.utc)
        mock_appointment.end_time = datetime(2026, 4, 25, 16, 0, tzinfo=timezone.utc)
        mock_appointment.type = "visit"
        mock_appointment.status = "confirmed"
        
        result = format_appointment_confirmation(mock_appointment, "Casa en Posadas")
        
        assert "Cita Agendada" in result
        assert "25/04/2026" in result
        assert "15:00" in result
        assert "Casa en Posadas" in result
    
    def test_format_appointment_list_empty(self):
        """Test de lista vacía."""
        result = format_appointment_list([])
        
        assert "No tienes citas" in result
    
    def test_format_appointment_list_with_data(self):
        """Test de lista con citas."""
        apt1 = MagicMock()
        apt1.id = uuid4()
        apt1.start_time = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
        apt1.property_id = uuid4()
        apt1.type = "visit"
        
        apt2 = MagicMock()
        apt2.id = uuid4()
        apt2.start_time = datetime(2026, 4, 26, 14, 0, tzinfo=timezone.utc)
        apt2.property_id = uuid4()
        apt2.type = "signing"
        
        result = format_appointment_list([apt1, apt2])
        
        assert "Tus próximas citas" in result
        assert "25/04" in result
        assert "26/04" in result


__all__ = ["TestFormattingFunctions"]