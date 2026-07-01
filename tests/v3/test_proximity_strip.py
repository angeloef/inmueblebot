"""Landmark proximity-prefix stripping for zone/reference-point search.

Regression: the LLM sometimes passes the whole phrase ("cerca de la municipalidad")
as ``zona`` instead of the landmark noun. Since matching is substring, the phrase
never hits "Municipalidad de Oberá". ``_strip_proximity`` removes the leading
proximity prefix so the landmark alone remains.
"""

import pytest

from app.tools.v2.search_properties import _strip_proximity


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("cerca de la municipalidad", "municipalidad"),
        ("cerca del hospital", "hospital"),
        ("cerca de la terminal", "terminal"),
        ("cerca de plaza", "plaza"),
        ("a 3 cuadras del hospital", "hospital"),
        ("a 2 cuadras de la plaza", "plaza"),
        ("frente al parque", "parque"),
        ("frente a la universidad", "universidad"),
        ("junto a la universidad", "universidad"),
        ("por la zona de la catedral", "catedral"),
        # Plain zones must pass through untouched (no proximity keyword).
        ("Centro", "Centro"),
        ("Barrio Schuster", "Barrio Schuster"),
        ("El Palmar", "El Palmar"),
        # Degenerate: only a prefix, no landmark -> keep original (never empty).
        ("cerca de", "cerca de"),
        ("", ""),
    ],
)
def test_strip_proximity(raw, expected):
    assert _strip_proximity(raw) == expected
