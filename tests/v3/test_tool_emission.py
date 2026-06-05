"""V3 tool-emission / selection backstops (engine determinism).

These lock in the deterministic fixes that make search results reach the user and
make booking finalize even when the LLM is inconsistent:

  - _persist_search_context: parse property ids from a search result string so the
    NEXT turn can resolve positional references.
  - _resolve_ordinal_to_id: map "la primera" / "el tercero" / "la última" to a
    concrete id from the previous search.
  - _execute_tools property_id backfill: a property-scoped tool called without a
    property_id inherits belief.selected_property_id (set by the engine or the
    ordinal backstop), so a dropped id can't break details / photos / booking.

Offline: no DB / Redis / LLM. The registry tool call is stubbed to capture args.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.tools.v2.registry  # noqa: F401 — ensure submodule bound for patch path
from app.routers.v3 import engine
from app.routers.v3.schema import ToolCallSpec


# ── _resolve_ordinal_to_id ──────────────────────────────────────────────────────

class TestResolveOrdinal:
    IDS = [12, 7, 3, 99]

    def test_primera(self):
        assert engine._resolve_ordinal_to_id("me interesa la primera", self.IDS) == 12

    def test_segunda(self):
        assert engine._resolve_ordinal_to_id("la segunda opción, ¿qué más sabés?", self.IDS) == 7

    def test_tercero(self):
        assert engine._resolve_ordinal_to_id("contame del tercero", self.IDS) == 3

    def test_ultima(self):
        assert engine._resolve_ordinal_to_id("mostrame la última", self.IDS) == 99

    def test_no_ordinal_returns_none(self):
        assert engine._resolve_ordinal_to_id("quiero algo más barato", self.IDS) is None

    def test_no_ids_returns_none(self):
        assert engine._resolve_ordinal_to_id("la primera", []) is None

    def test_ordinal_out_of_range_returns_none(self):
        # only one result, but user says "la tercera" → no id to map to
        assert engine._resolve_ordinal_to_id("la tercera", [5]) is None


# ── _persist_search_context ──────────────────────────────────────────────────────

class TestPersistSearchContext:
    def _belief(self):
        return SimpleNamespace(last_search_ids=[], last_search_count=0, last_search_context="")

    def test_extracts_ids_in_order(self):
        belief = self._belief()
        result = (
            "Encontre 2 propiedades:\n"
            "  [12] departamento en Centro -- $250.000/mes\n"
            "       2 dorm, 50m2\n"
            "  [7] casa en Schuster -- $400.000\n"
        )
        engine._persist_search_context(belief, ["search_properties"], [result])
        assert belief.last_search_ids == [12, 7]
        assert belief.last_search_count == 2
        assert "[12]" in belief.last_search_context

    def test_no_search_tool_is_noop(self):
        belief = self._belief()
        engine._persist_search_context(belief, ["get_faq_answer"], ["alguna respuesta"])
        assert belief.last_search_ids == []

    def test_handles_empty_result_string(self):
        belief = self._belief()
        engine._persist_search_context(belief, ["search_properties"], [""])
        assert belief.last_search_ids == []


# ── _execute_tools property_id backfill ─────────────────────────────────────────

def _turn_with_tool(name: str, arguments: str = "{}"):
    return SimpleNamespace(tool_calls=[ToolCallSpec(name=name, arguments=arguments)])


class TestPropertyIdBackfill:
    @pytest.mark.asyncio
    async def test_missing_property_id_is_backfilled_from_selection(self):
        captured = {}

        async def _fake_execute(call):
            captured["args"] = call.arguments
            captured["name"] = call.name
            return "ok"

        belief = SimpleNamespace(selected_property_id=42)
        turn = _turn_with_tool("get_property_details", "{}")

        with patch("app.tools.v2.registry.execute_tool", AsyncMock(side_effect=_fake_execute)):
            tools_used, _results, any_ran, _booked = await engine._execute_tools(turn, belief)

        assert any_ran is True
        assert tools_used == ["get_property_details"]
        assert captured["args"].get("property_id") == 42

    @pytest.mark.asyncio
    async def test_explicit_property_id_is_not_overwritten(self):
        captured = {}

        async def _fake_execute(call):
            captured["args"] = call.arguments
            return "ok"

        belief = SimpleNamespace(selected_property_id=42)
        turn = _turn_with_tool("get_property_images", '{"property_id": 9}')

        with patch("app.tools.v2.registry.execute_tool", AsyncMock(side_effect=_fake_execute)):
            await engine._execute_tools(turn, belief)

        assert captured["args"].get("property_id") == 9  # engine's explicit id wins

    @pytest.mark.asyncio
    async def test_schedule_visit_inherits_selection_for_booking(self):
        captured = {}

        async def _fake_execute(call):
            captured["args"] = call.arguments
            # emit the structural success marker so booking_succeeded flips True
            return "Cita agendada.\n<!--CONFIRMED:2026-06-06 16:00-->"

        belief = SimpleNamespace(selected_property_id=7)
        turn = _turn_with_tool("schedule_visit", '{"dia": "jueves", "horario": "16:00", "nombre": "Juan"}')

        with patch("app.tools.v2.registry.execute_tool", AsyncMock(side_effect=_fake_execute)):
            _tools, _results, _any, booking_succeeded = await engine._execute_tools(turn, belief)

        assert captured["args"].get("property_id") == 7
        assert booking_succeeded is True

    @pytest.mark.asyncio
    async def test_no_selection_skips_property_tool(self):
        """With no selection AND no engine-supplied id, get_property_details (which
        requires property_id) is validated-out and never executed — no crash."""
        called = []

        async def _fake_execute(call):
            called.append(call)
            return "ok"

        belief = SimpleNamespace(selected_property_id=None)
        turn = _turn_with_tool("get_property_details", "{}")

        with patch("app.tools.v2.registry.execute_tool", AsyncMock(side_effect=_fake_execute)):
            tools_used, _results, any_ran, _booked = await engine._execute_tools(turn, belief)

        assert called == []          # tool skipped at validation, never executed
        assert any_ran is False
        assert tools_used == []


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
