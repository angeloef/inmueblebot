"""V3 deterministic photo delivery (manual-test-5 fixes).

Locks in the structural fix for the "promised photos, never sent" bug: photo
delivery must be driven by get_property_images RUNNING, not by the engine emitting
a redundant 'images' segment in response_plan (which it did inconsistently — the
photos were silently dropped and the user was left waiting).

Also covers the UX shape the fix guarantees:
  - images carry NO caption (no repeated text under every photo)
  - a single visit CTA follows the photos as a separate text segment

Offline: _resolve_images is stubbed so no DB / tool / network is touched.
Tests are async (suite runs under asyncio mode=auto) to avoid closing the shared
event loop, which would pollute sibling tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers.v3 import engine
from app.routers.v3.engine import _PHOTO_CTA_ES, _MAX_PHOTOS
from app.routers.v3.schema import ResponsePlanItem, TurnOutput, BeliefDelta


def _belief(selected_id: int | None = 45):
    return SimpleNamespace(
        selected_property_id=selected_id,
        search_criteria={},
        active_intents=set(),
    )


def _turn(action: str, plan: list[ResponsePlanItem], tool_calls=None):
    return TurnOutput(
        belief_delta=BeliefDelta(),
        intent="search",
        action=action,
        tool_calls=tool_calls or [],
        selected_property_id=None,
        missing_slot=None,
        response_plan=plan,
        confidence=0.99,
    )


_FAKE_IMAGES = (["http://x/0", "http://x/1", "http://x/2"], "Casa Hospital Samic")


@patch.object(engine, "_resolve_images", new_callable=AsyncMock)
async def test_photos_delivered_even_when_engine_emits_only_text(mock_resolve):
    """The production bug: action=show_photos, get_property_images ran, but the
    engine's response_plan was a TEXT filler ("Te muestro las fotos de ID:45").
    Photos must still be delivered."""
    mock_resolve.return_value = _FAKE_IMAGES
    turn = _turn(
        "show_photos",
        plan=[ResponsePlanItem(type="text", content="Te muestro las fotos de la ID:45.")],
    )
    text, rich, _source = await engine._assemble_response(
        turn, _belief(45), tool_results=["{...}"], any_ran=True,
        tenant_id=None, tools_used=["get_property_images"],
    )
    plan = rich["response_plan"]
    assert plan[0]["type"] == "images"
    assert plan[0]["images"] == _FAKE_IMAGES[0]
    assert plan[-1]["type"] == "text"
    assert plan[-1]["content"] == _PHOTO_CTA_ES
    assert text == _PHOTO_CTA_ES  # recorded in history for next-turn context


@patch.object(engine, "_resolve_images", new_callable=AsyncMock)
async def test_photos_have_no_repeated_caption(mock_resolve):
    mock_resolve.return_value = _FAKE_IMAGES
    turn = _turn("show_photos", plan=[ResponsePlanItem(type="text", content="x")])
    _text, rich, _source = await engine._assemble_response(
        turn, _belief(45), tool_results=["{}"], any_ran=True,
        tenant_id=None, tools_used=["get_property_images"],
    )
    img_seg = rich["response_plan"][0]
    assert img_seg["caption"] == ""


@patch.object(engine, "_resolve_images", new_callable=AsyncMock)
async def test_photos_capped_at_max(mock_resolve):
    many = [f"http://x/{i}" for i in range(10)]
    mock_resolve.return_value = (many, "T")
    turn = _turn("show_photos", plan=[ResponsePlanItem(type="text", content="x")])
    _text, rich, _source = await engine._assemble_response(
        turn, _belief(45), tool_results=["{}"], any_ran=True,
        tenant_id=None, tools_used=["get_property_images"],
    )
    assert len(rich["response_plan"][0]["images"]) == _MAX_PHOTOS


@patch.object(engine, "_resolve_images", new_callable=AsyncMock)
async def test_falls_through_to_text_when_no_images_resolved(mock_resolve):
    """If the property genuinely has no photos, don't pretend — fall through to the
    engine's text reply instead of an empty image plan."""
    mock_resolve.return_value = ([], "")
    turn = _turn(
        "show_photos",
        plan=[ResponsePlanItem(type="text", content="No tengo fotos de esa.")],
    )
    text, rich, _source = await engine._assemble_response(
        turn, _belief(45), tool_results=["{}"], any_ran=True,
        tenant_id=None, tools_used=["get_property_images"],
    )
    assert "response_plan" not in rich or not rich.get("response_plan")
    assert text == "No tengo fotos de esa."


@patch.object(engine, "_resolve_images", new_callable=AsyncMock)
async def test_engine_images_segment_also_routes_through_builder(mock_resolve):
    """Legacy path: engine emits an 'images' segment but did NOT call the tool.
    Still delivered with no caption + CTA."""
    mock_resolve.return_value = _FAKE_IMAGES
    turn = _turn(
        "show_photos",
        plan=[ResponsePlanItem(type="images", content="Fotos ID:45")],
    )
    text, rich, _source = await engine._assemble_response(
        turn, _belief(45), tool_results=[], any_ran=False,
        tenant_id=None, tools_used=[],
    )
    plan = rich["response_plan"]
    assert plan[0]["type"] == "images" and plan[0]["caption"] == ""
    assert plan[-1]["content"] == _PHOTO_CTA_ES
