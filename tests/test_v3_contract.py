"""Contract parity tests for the V3 adapter (Phase 2).

Verifies that ``process_turn_v3`` returns the GUARANTEED subset of keys that
``process_turn_v2`` always returns, so the webhook + WhatsApp sender never break
when traffic is routed to V3.

Guaranteed subset (always present, per the compatibility contract in the build plan §3):
    response_text   str
    tools_used      list
    rich_content    dict
    confidence      float | int
    router_label    str
    latency_ms      float | int

The ``messages`` and ``rich_content.response_plan`` keys are NOT guaranteed (they
appear only in multi-message turns in V2 too).

These tests run OFFLINE — no DB / Redis / LLM / network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# Guaranteed keys the webhook and WhatsApp sender consume unconditionally.
_GUARANTEED = frozenset({
    "response_text",
    "tools_used",
    "rich_content",
    "confidence",
    "router_label",
    "latency_ms",
})


@pytest.mark.asyncio
async def test_process_turn_v3_returns_guaranteed_keys() -> None:
    """V3 adapter must return the guaranteed-subset keys for a normal message."""
    from app.routers.v3.adapter import process_turn_v3

    result = await process_turn_v3(
        phone="549test1234",
        user_message="Hola, busco un departamento en alquiler.",
    )

    missing = _GUARANTEED - result.keys()
    assert not missing, f"process_turn_v3 missing guaranteed keys: {missing}"


@pytest.mark.asyncio
async def test_process_turn_v3_types() -> None:
    """Guaranteed keys have the correct types."""
    from app.routers.v3.adapter import process_turn_v3

    result = await process_turn_v3(
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
async def test_process_turn_v3_with_tenant_uuid() -> None:
    """Passing a valid UUID as tenant must not raise and must return the contract dict."""
    from app.routers.v3.adapter import process_turn_v3

    result = await process_turn_v3(
        phone="549test9999",
        user_message="¿Cuál es el precio del departamento?",
        tenant="00000000-0000-0000-0000-000000000001",
    )

    assert _GUARANTEED.issubset(result.keys())
    assert result["router_label"].startswith("v3::")


@pytest.mark.asyncio
async def test_process_turn_v3_error_fallback() -> None:
    """Even if the engine raises, the adapter returns a valid contract dict (no crash)."""
    from app.routers.v3.adapter import process_turn_v3

    with patch(
        "app.routers.v3.engine.run_turn",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        result = await process_turn_v3(
            phone="549test0000",
            user_message="Hola.",
        )

    assert _GUARANTEED.issubset(result.keys())
    assert result["router_label"] == "v3::error"
    assert result["confidence"] == 0.0
    assert isinstance(result["response_text"], str)
    assert len(result["response_text"]) > 0


@pytest.mark.asyncio
async def test_process_turn_v3_parity_with_v2_keys() -> None:
    """The guaranteed subset of V3 is a subset of V2's always-present keys.

    This verifies that V3 doesn't accidentally drop a key V2 always returns, so the
    webhook can be switched without touching any downstream code.
    """
    from app.routers.v3.adapter import process_turn_v3

    v3_result = await process_turn_v3(
        phone="549test5555",
        user_message="Busco terreno.",
    )

    assert _GUARANTEED.issubset(v3_result.keys()), (
        "V3 must return at least the same guaranteed keys as V2. "
        f"Missing: {_GUARANTEED - v3_result.keys()}"
    )
