"""Google Places API (New) — city autocomplete proxy.

Server-side ONLY. The Places API key NEVER reaches the browser: the dashboard calls
our /admin endpoint, which calls Google here with the key. Uses the New Places
Autocomplete REST endpoint with an "IDs Only" field mask (free tier) restricted to
localities (cities), biased to AR/PY.

Graceful degradation: if the key is unset OR the request fails, returns [] so the
city field stays usable as free text. Never raises to the caller.
"""
from __future__ import annotations

import httpx
from loguru import logger

from app.core.config import get_settings

_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
_FIELD_MASK = "suggestions.placePrediction.placeId,suggestions.placePrediction.text"
_TIMEOUT_SECONDS = 6.0
_MIN_QUERY_LEN = 2


async def autocomplete_cities(query: str) -> list[dict]:
    """Return city suggestions as ``[{"place_id": str, "description": str}, ...]``.

    Empty list when the key is missing, the query is too short, or Google errors.
    """
    q = (query or "").strip()
    if len(q) < _MIN_QUERY_LEN:
        return []

    settings = get_settings()
    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        logger.info("GooglePlaces: API key no configurada — autocompletado vacío (texto libre)")
        return []

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": _FIELD_MASK,
    }
    body = {
        "input": q,
        "includedPrimaryTypes": ["(cities)"],
        "includedRegionCodes": ["ar", "py"],
        "languageCode": "es",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT_SECONDS, connect=4.0)) as client:
            resp = await client.post(_AUTOCOMPLETE_URL, headers=headers, json=body)
    except Exception as exc:
        logger.warning(f"GooglePlaces: request falló ({exc!r}) — autocompletado vacío")
        return []

    if resp.status_code != 200:
        # Log solo el status estructurado de Google (no el body crudo) para no
        # arrastrar nada sensible a los logs.
        try:
            err_status = (resp.json().get("error") or {}).get("status", "UNKNOWN")
        except Exception:
            err_status = "non-JSON"
        logger.warning(
            f"GooglePlaces: HTTP {resp.status_code} ({err_status}) — autocompletado vacío"
        )
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    out: list[dict] = []
    for s in data.get("suggestions", []):
        pred = s.get("placePrediction") or {}
        place_id = pred.get("placeId")
        text = (pred.get("text") or {}).get("text") or ""
        if place_id and text:
            out.append({"place_id": place_id, "description": text})
    return out
