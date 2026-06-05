"""Phase 7 — Failure-drill tests (fail-open guarantees).

The build plan (Phase 7) requires that EVERY failure mode degrades to a safe
Spanish message and NEVER crashes the webhook:

    LLM timeout · malformed structured output · tool exception · Redis down · DB down

These tests exercise each drill at the layer that owns the guarantee:

  - ``_call_engine``  never raises → ``(None, usage)`` on client error / refusal /
    unparseable content (LLM timeout + malformed structured output drills).
  - ``run_turn``      returns a valid contract dict even when belief I/O (Redis)
    raises, when the engine yields nothing, and when a tool blows up.
  - ``process_turn_v3`` (adapter) converts an unexpected ``run_turn`` crash into the
    ``v3::error`` contract (DB-down / unknown-crash drill).
  - the structural anti-hallucination guard still holds when a booking tool FAILS
    (no fake "Cita Agendada" can leak under failure).

All offline: no DB / Redis / LLM / network. External boundaries are stubbed; the
real engine logic runs so the fail-open paths are genuinely exercised.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# Import the modules we patch so their parent-package attributes exist before
# ``mock.patch`` traverses the dotted target paths (the engine imports these
# lazily inside functions, so they are not auto-bound on the ``app`` package).
import app.agents.cs_llm_client  # noqa: F401
import app.routers.v3.belief  # noqa: F401
import app.routers.v3.engine  # noqa: F401
import app.routers.v3.guard  # noqa: F401
import app.routers.v3.scheduling.fsm  # noqa: F401
import app.tools.v2.registry  # noqa: F401

from app.routers.v3.engine import _SAFE_CLARIFY_ES

_GUARANTEED = frozenset({
    "response_text", "tools_used", "rich_content",
    "confidence", "router_label", "latency_ms",
})


def _assert_contract(result: dict) -> None:
    """Every fail-open path must still satisfy the frozen V2 contract."""
    assert _GUARANTEED.issubset(result.keys()), f"missing keys: {_GUARANTEED - result.keys()}"
    assert isinstance(result["response_text"], str) and result["response_text"].strip()
    assert isinstance(result["tools_used"], list)
    assert isinstance(result["rich_content"], dict)
    assert isinstance(result["confidence"], float | int)
    assert isinstance(result["router_label"], str)
    assert isinstance(result["latency_ms"], float | int)


# ── Fake OpenAI client plumbing for _call_engine drills ─────────────────────────

def _fake_client(*, raises: Exception | None = None, content=None, refusal=None):
    """Build a fake AsyncOpenAI-shaped client for ``_call_engine``."""
    async def _create(**_kwargs):
        if raises is not None:
            raise raises
        message = SimpleNamespace(content=content, refusal=refusal)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None)
        return SimpleNamespace(choices=[choice], usage=usage)

    completions = SimpleNamespace(create=_create)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def _patch_engine_client(client):
    """Patch the LLM client factory the engine uses (both get_client + get_model)."""
    return patch.multiple(
        "app.agents.cs_llm_client",
        get_client=lambda *a, **k: client,
        get_model=lambda *a, **k: "gpt-5.4-mini",
    )


# ── Drill 1 + 2: LLM timeout / malformed structured output (engine call layer) ──

class TestCallEngineNeverRaises:
    """``_call_engine`` absorbs every LLM failure mode into (None, usage)."""

    @pytest.mark.asyncio
    async def test_client_timeout_returns_none_none(self) -> None:
        from app.routers.v3.engine import _call_engine

        with _patch_engine_client(_fake_client(raises=TimeoutError("LLM timeout"))):
            turn, usage = await _call_engine([{"role": "user", "content": "hola"}])

        assert turn is None
        assert usage is None  # call never produced a usage object

    @pytest.mark.asyncio
    async def test_malformed_json_content_returns_none(self) -> None:
        from app.routers.v3.engine import _call_engine

        with _patch_engine_client(_fake_client(content="not-valid-json {{{")):
            turn, usage = await _call_engine([{"role": "user", "content": "hola"}])

        assert turn is None
        assert usage is not None  # the call SUCCEEDED, only parsing failed

    @pytest.mark.asyncio
    async def test_refusal_returns_none(self) -> None:
        from app.routers.v3.engine import _call_engine

        with _patch_engine_client(_fake_client(refusal="No puedo ayudar con eso")):
            turn, usage = await _call_engine([{"role": "user", "content": "hola"}])

        assert turn is None

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self) -> None:
        from app.routers.v3.engine import _call_engine

        with _patch_engine_client(_fake_client(content=None)):
            turn, usage = await _call_engine([{"role": "user", "content": "hola"}])

        assert turn is None


# ── run_turn fail-open drills (stub the I/O boundaries, run the real engine) ─────

def _fresh_belief(session_id: str = "drill-session"):
    from app.routers.v3.belief import BeliefStateV5
    return BeliefStateV5(session_id=session_id)


def _patch_run_turn_io(*, load_raises=False, save_raises=False):
    """Stub Redis belief I/O, the quality guard, and the FSM so run_turn is offline.

    The engine call itself is left to the per-test patch so each drill controls it.
    """
    patchers = []

    if load_raises:
        load = AsyncMock(side_effect=RuntimeError("Redis down"))
    else:
        load = AsyncMock(return_value=_fresh_belief())
    patchers.append(patch("app.routers.v3.belief.load_belief_v5", load))

    if save_raises:
        save = AsyncMock(side_effect=RuntimeError("Redis down"))
    else:
        save = AsyncMock(return_value=None)
    patchers.append(patch("app.routers.v3.belief.save_belief_v5", save))

    # Quality guard + FSM call the LLM/DB; neutralise them (they already fail-open,
    # but we keep the drill offline & deterministic).
    guard_passthrough = AsyncMock(side_effect=lambda **kw: SimpleNamespace(
        response_text=kw["response_text"], judge_score=None, regenerated=False,
    ))
    patchers.append(patch("app.routers.v3.guard.run_guard", guard_passthrough))
    patchers.append(patch("app.routers.v3.scheduling.fsm.resolve", AsyncMock(return_value=None)))

    return patchers


class _PatchSet:
    """Apply / tear down a list of patchers as one context manager."""

    def __init__(self, patchers):
        self._patchers = patchers

    def __enter__(self):
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patchers):
            p.stop()
        return False


class TestRunTurnFailsOpen:
    """run_turn returns a valid contract on every degraded dependency."""

    @pytest.mark.asyncio
    async def test_llm_timeout_falls_back_to_safe_clarify(self) -> None:
        """Engine yields nothing (timeout) → regex fallback → safe Spanish clarify."""
        from app.routers.v3 import engine

        with _PatchSet(_patch_run_turn_io()):
            with patch.object(engine, "_call_engine", AsyncMock(return_value=(None, None))):
                result = await engine.run_turn(
                    phone="549drill1", user_message="askljdfh qwoiuer",
                )

        _assert_contract(result)
        assert result["response_text"] == _SAFE_CLARIFY_ES
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_redis_down_on_load_still_returns(self) -> None:
        """load_belief_v5 raising (Redis down) must not crash the turn."""
        from app.routers.v3 import engine

        with _PatchSet(_patch_run_turn_io(load_raises=True)):
            with patch.object(engine, "_call_engine", AsyncMock(return_value=(None, None))):
                result = await engine.run_turn(
                    phone="549drill2", user_message="busco depto",
                )

        _assert_contract(result)

    @pytest.mark.asyncio
    async def test_redis_down_on_save_still_returns(self) -> None:
        """save_belief_v5 raising must not crash the turn."""
        from app.routers.v3 import engine

        with _PatchSet(_patch_run_turn_io(save_raises=True)):
            with patch.object(engine, "_call_engine", AsyncMock(return_value=(None, None))):
                result = await engine.run_turn(
                    phone="549drill3", user_message="busco casa",
                )

        _assert_contract(result)

    @pytest.mark.asyncio
    async def test_tool_exception_does_not_crash_or_fake_booking(self) -> None:
        """A tool raising mid-turn is caught; no fake booking confirmation leaks."""
        from app.routers.v3 import engine
        from app.routers.v3.schema import (
            TurnOutput, BeliefDelta, ToolCallSpec, ResponsePlanItem,
        )

        # Engine "decides" to book and even drafts a confirmation, but the tool fails.
        booking_turn = TurnOutput(
            belief_delta=BeliefDelta(),
            intent="scheduling",
            action="book_step",
            tool_calls=[ToolCallSpec(name="schedule_visit", arguments="{}")],
            selected_property_id=None,
            missing_slot=None,
            response_plan=[ResponsePlanItem(
                type="text",
                content="📅 *¡Cita Agendada!* Tu visita está confirmada.",
            )],
            confidence=0.95,
        )

        with _PatchSet(_patch_run_turn_io()):
            with patch.object(engine, "_call_engine", AsyncMock(return_value=(booking_turn, None))):
                with patch(
                    "app.tools.v2.registry.execute_tool",
                    AsyncMock(side_effect=RuntimeError("DB down")),
                ):
                    result = await engine.run_turn(
                        phone="549drill4", user_message="el viernes a las 3",
                    )

        _assert_contract(result)
        # Structural anti-hallucination: no confirmation may survive a failed booking.
        lowered = result["response_text"].lower()
        assert "cita agendada" not in lowered
        assert "confirmada" not in lowered
        assert "<!--confirmed" not in lowered


# ── Drill: adapter converts an unexpected crash into v3::error (DB-down / unknown) ──

class TestAdapterFailOpen:
    @pytest.mark.asyncio
    async def test_unexpected_run_turn_crash_becomes_v3_error(self) -> None:
        from app.routers.v3.adapter import process_turn_v3

        with patch(
            "app.routers.v3.engine.run_turn",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unrecoverable DB failure"),
        ):
            result = await process_turn_v3(phone="549drill5", user_message="hola")

        _assert_contract(result)
        assert result["router_label"] == "v3::error"
        assert result["confidence"] == 0.0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
