"""Tests for the Google Places city-autocomplete proxy (server-side key, graceful empty)."""
from __future__ import annotations

import httpx
import pytest

from app.core import config


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


async def test_autocomplete_empty_when_key_unset(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    config.get_settings.cache_clear()
    from app.integrations import google_places

    result = await google_places.autocomplete_cities("Obe")
    assert result == []


async def test_autocomplete_parses_google_response(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    config.get_settings.cache_clear()
    from app.integrations import google_places

    google_payload = {
        "suggestions": [
            {"placePrediction": {"placeId": "ChIJ_OBERA", "text": {"text": "Oberá, Misiones, Argentina"}}},
            {"placePrediction": {"placeId": "ChIJ_POSADAS", "text": {"text": "Posadas, Misiones, Argentina"}}},
        ]
    }

    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json=google_payload)

    transport = httpx.MockTransport(_handler)
    real_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(google_places.httpx, "AsyncClient", _client_factory)

    result = await google_places.autocomplete_cities("Obe")
    assert result == [
        {"place_id": "ChIJ_OBERA", "description": "Oberá, Misiones, Argentina"},
        {"place_id": "ChIJ_POSADAS", "description": "Posadas, Misiones, Argentina"},
    ]
    assert captured["headers"].get("X-Goog-Api-Key") == "test-key"


async def test_autocomplete_short_query_returns_empty(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test-key")
    config.get_settings.cache_clear()
    from app.integrations import google_places

    assert await google_places.autocomplete_cities("O") == []


def test_property_create_update_persists_place_id():
    from app.api.routes.admin import PropertyCreate, _prop_to_dict

    pc = PropertyCreate(city="Oberá", place_id="ChIJ_OBERA")
    assert pc.place_id == "ChIJ_OBERA"

    class _FakeProp:
        extra_data = {"city": "Oberá", "place_id": "ChIJ_OBERA", "zone": "Centro", "street": "Calle 1"}
        location = "Calle 1, Centro, Oberá"
        id = 1
        title = "t"
        description = ""
        category = "casa"
        price = 1
        bedrooms = 1
        bathrooms = 1
        area_m2 = 1
        images = []
        status = "available"
        type = "venta"
        currency = "ARS"
        reference_points = []
        created_at = None
        updated_at = None

    d = _prop_to_dict(_FakeProp(), include_images=False)
    assert d["place_id"] == "ChIJ_OBERA"
    assert d["city"] == "Oberá"
