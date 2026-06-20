"""test_thumbnail.py — Unit del generador de miniaturas WebP (plan 40).

Corre sin Postgres: solo Pillow + la función pura make_webp_thumb.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

from app.api.routes.admin import make_webp_thumb


def _png_bytes(w: int, h: int) -> bytes:
    img = Image.new("RGB", (w, h), (120, 30, 200))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_output_is_webp():
    thumb = make_webp_thumb(_png_bytes(1000, 500))
    # Firma RIFF....WEBP
    assert thumb[:4] == b"RIFF"
    assert thumb[8:12] == b"WEBP"


def test_scales_down_preserving_aspect_ratio():
    thumb = make_webp_thumb(_png_bytes(1000, 500), max_side=400)
    img = Image.open(io.BytesIO(thumb))
    assert max(img.size) == 400          # lado mayor escalado al tope
    assert img.size == (400, 200)        # aspect ratio 2:1 preservado


def test_does_not_upscale_small_images():
    thumb = make_webp_thumb(_png_bytes(100, 80), max_side=400)
    img = Image.open(io.BytesIO(thumb))
    assert img.size == (100, 80)         # no se agranda


def test_thumb_is_lighter_than_native_png():
    native = _png_bytes(1200, 900)
    thumb = make_webp_thumb(native)
    assert len(thumb) < len(native)


def test_invalid_bytes_raise_valueerror():
    with pytest.raises(ValueError):
        make_webp_thumb(b"not an image")
