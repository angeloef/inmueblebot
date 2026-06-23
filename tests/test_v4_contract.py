"""Contract parity tests for the V4 adapter (KA0 scaffold).

Same guaranteed-subset contract as V3/V2:
    response_text, tools_used, rich_content, confidence, router_label, latency_ms

These tests run OFFLINE — no DB / Redis / LLM / network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

_GUARANTEED = frozenset({
    "response_text",
    "tools_used",
    "rich_content",
    "confidence",
    "router_label",
    "latency_ms",
})

_V3_STUB_RESULT = {
    "response_text": "Hola, ¿en qué te puedo ayudar?",
    "tools_used": [],
    "rich_content": {},
    "confidence": 0.9,
    "router_label": "v3::smalltalk",
    "latency_ms": 100.0,
}


@pytest.fixture(autouse=True)
def _no_inbox_side_effects():
    with patch("app.routers.v4.adapter._persist_turn_v4", new_callable=AsyncMock), \
         patch("app.routers.v4.adapter._handle_handoff_v4", new_callable=AsyncMock):
        yield


@pytest.mark.asyncio
async def test_process_turn_v4_returns_guaranteed_keys() -> None:
    from app.routers.v4.adapter import process_turn_v4

    with patch("app.routers.v3.engine.run_turn", new_callable=AsyncMock, return_value=_V3_STUB_RESULT):
        result = await process_turn_v4(
            phone="549test1234",
            user_message="Hola, busco un departamento en alquiler.",
        )

    missing = _GUARANTEED - result.keys()
    assert not missing, f"process_turn_v4 missing guaranteed keys: {missing}"


@pytest.mark.asyncio
async def test_process_turn_v4_types() -> None:
    from app.routers.v4.adapter import process_turn_v4

    with patch("app.routers.v3.engine.run_turn", new_callable=AsyncMock, return_value=_V3_STUB_RESULT):
        result = await process_turn_v4(
            phone="549test1234",
            user_message="Quiero ver casas en venta.",
        )

    assert isinstance(result["response_text"], str)
    assert isinstance(result["tools_used"], list)
    assert isinstance(result["rich_content"], dict)
    assert isinstance(result["confidence"], float | int)
    assert isinstance(result["router_label"], str)
    assert isinstance(result["latency_ms"], float | int)


@pytest.mark.asyncio
async def test_process_turn_v4_with_tenant_uuid() -> None:
    from app.routers.v4.adapter import process_turn_v4

    with patch("app.routers.v3.engine.run_turn", new_callable=AsyncMock, return_value=_V3_STUB_RESULT):
        result = await process_turn_v4(
            phone="549test9999",
            user_message="¿Cuál es el precio del departamento?",
            tenant="00000000-0000-0000-0000-000000000001",
        )

    assert _GUARANTEED.issubset(result.keys())


@pytest.mark.asyncio
async def test_process_turn_v4_error_fallback() -> None:
    from app.routers.v4.adapter import process_turn_v4

    with patch(
        "app.routers.v4.engine.run_turn",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        result = await process_turn_v4(
            phone="549test0000",
            user_message="Hola.",
        )

    assert _GUARANTEED.issubset(result.keys())
    assert result["router_label"] == "v4::error"
    assert result["confidence"] == 0.0
    assert len(result["response_text"]) > 0


@pytest.mark.asyncio
async def test_process_turn_v4_emergency_gate() -> None:
    """Emergency gate fires without LLM, returns v4::emergency label."""
    from app.routers.v4.adapter import process_turn_v4

    result = await process_turn_v4(
        phone="549test1111",
        user_message="hay un incendio en el edificio ayuda urgente",
    )

    assert result["router_label"] == "v4::emergency"
    assert result["confidence"] == 1.0
    assert _GUARANTEED.issubset(result.keys())


@pytest.mark.asyncio
async def test_process_turn_v4_human_handoff_gate() -> None:
    """Human-handoff gate fires without LLM, returns v4::human-handoff label."""
    from app.routers.v4.adapter import process_turn_v4

    result = await process_turn_v4(
        phone="549test2222",
        user_message="quiero hablar con una persona real",
    )

    assert result["router_label"] == "v4::human-handoff"
    assert "request_human_assistance" in result["tools_used"]
    assert _GUARANTEED.issubset(result.keys())
