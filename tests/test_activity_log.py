"""Tests del helper de activity_log.

Propiedad crítica: registrar actividad **nunca** debe abortar la operación de
negocio. Si la sesión falla al agregar/flushear la fila, el helper traga la
excepción y loguea, sin propagar.
"""

from __future__ import annotations

import pytest

from app.services.activity_log_service import log_activity, log_activity_async


class _BoomSession:
    """Sesión sync que explota en add()/flush() — simula DB caída o tabla ausente."""

    def add(self, _obj):
        raise RuntimeError("db down")

    def flush(self):
        raise RuntimeError("db down")


class _RecordingSession:
    """Sesión sync mínima que registra lo agregado."""

    def __init__(self):
        self.added = []
        self.flushed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed = True


def test_log_activity_swallows_errors_and_never_raises():
    # Arrange
    session = _BoomSession()

    # Act / Assert — no debe propagar
    log_activity(
        session,
        tenant_id=None,
        entity_type="property",
        entity_id="123",
        action="status_changed",
        payload={"from": "available", "to": "rented"},
    )


def test_log_activity_adds_row_with_expected_fields():
    # Arrange
    session = _RecordingSession()

    # Act
    log_activity(
        session,
        tenant_id=None,
        entity_type="property",
        entity_id=456,
        action="property_edited",
        payload={"changes": {"price": {"from": 100, "to": 90}}},
    )

    # Assert
    assert session.flushed is True
    assert len(session.added) == 1
    row = session.added[0]
    assert row.entity_type == "property"
    assert row.entity_id == "456"  # int → str
    assert row.action == "property_edited"
    assert row.actor == "dashboard"
    assert row.payload == {"changes": {"price": {"from": 100, "to": 90}}}


class _BoomAsyncSession:
    async def execute(self, *_args, **_kwargs):
        raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_log_activity_async_swallows_errors():
    # Arrange
    session = _BoomAsyncSession()

    # Act / Assert — no debe propagar
    await log_activity_async(
        session,
        tenant_id=None,
        entity_type="property",
        entity_id="789",
        action="reassigned",
        payload={"from_branch": "a", "to_branch": "b"},
    )
