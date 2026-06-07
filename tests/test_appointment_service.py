"""
Tests para el servicio de citas/appointments.
Ejecutar: pytest tests/test_appointment_service.py -v
"""
import asyncio

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import MagicMock

from app.services.appointment_service import (
    appointment_service,
    format_appointment_confirmation,
    format_appointment_list,
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
        # The formatter renders Argentina-local time (UTC-3): 15:00 UTC → 12:00 AR.
        assert "12:00" in result
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


class _CapturingResult:
    """Minimal stand-in for a SQLAlchemy Result."""

    def scalars(self):
        return self

    def first(self):
        return None


class _CapturingSession:
    """Async session double that records the query passed to ``execute``."""

    def __init__(self):
        self.captured = None

    async def execute(self, query):
        self.captured = query
        return _CapturingResult()


def _where_clause_of(query) -> str:
    """Return only the WHERE portion of the compiled SQL (lower-cased)."""
    sql = str(query).lower()
    # Everything after the first WHERE is the predicate we care about.
    return sql.split("where", 1)[1] if "where" in sql else ""


class TestConflictScope:
    """The conflict check is per-AGENCY, not per-property (one visit at a time).

    Regression for the double-booking bug: a colliding appointment on a *different*
    property (or with a NULL property_id) used to slip past a ``property_id == N``
    filter. The query must constrain status + time window, but NOT property_id.
    """

    def _build_query(self, exclude_id=None):
        sess = _CapturingSession()
        start = datetime(2026, 6, 9, 13, 0, tzinfo=timezone.utc)
        asyncio.run(
            appointment_service._check_conflict(
                sess, property_id=9, start_time=start,
                exclude_appointment_id=exclude_id,
            )
        )
        assert sess.captured is not None
        return sess.captured

    def test_conflict_query_does_not_filter_by_property(self):
        where = _where_clause_of(self._build_query())
        assert "property_id" not in where, (
            "conflict check must be per-agency — filtering by property_id "
            "reintroduces the double-booking bug"
        )

    def test_conflict_query_constrains_status_and_time_window(self):
        where = _where_clause_of(self._build_query())
        assert "status" in where
        assert "start_time" in where
        assert "end_time" in where

    def test_exclude_appointment_id_adds_id_filter(self):
        exclude = uuid4()
        where = _where_clause_of(self._build_query(exclude_id=exclude))
        assert "id !=" in where or "id <>" in where


__all__ = ["TestFormattingFunctions", "TestConflictScope"]