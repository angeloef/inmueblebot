"""Unit tests for the V3 client-side limits: abuse detection, daily-cap counter
fallback, the off-topic/abuse belief field, and the daily-cap message.

These cover the pure, deterministic pieces (no Redis / no LLM). The gate wiring in
engine.run_turn is exercised by the existing gate-history tests.
"""

import pytest

from app.routers.v3.abuse import is_abusive
from app.core import usage_limits
from app.routers.v3 import engine
from app.routers.v3.belief import BeliefStateV5, serialize_v5, deserialize_v5


# ── Abuse detection ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "sos un idiota",
    "que boludo el bot",
    "andate a la mierda",
    "son unos ladrones",
    "hijo de puta",
    "no servís para nada, inútil",
    "ESTÚPIDO bot",
])
def test_is_abusive_flags_insults(msg):
    assert is_abusive(msg) is True


@pytest.mark.parametrize("msg", [
    "busco departamento en alquiler",
    "hola, soy Gil, quiero ver una casa",   # name collision must NOT flag
    "tienen algo en el centro?",
    "necesito una computadora cerca",        # 'computadora' must NOT flag
    "gracias, muy amable",
    "",
])
def test_is_abusive_ignores_clean_messages(msg):
    assert is_abusive(msg) is False


# ── Daily-cap counter (in-process fallback path) ────────────────────────────────

def test_local_incr_counts_and_rolls_over():
    usage_limits._local_counts.clear()
    key = "t:daily_msg:2026-06-11:user-x"
    assert usage_limits._local_incr(key, "2026-06-11") == 1
    assert usage_limits._local_incr(key, "2026-06-11") == 2
    assert usage_limits._local_incr(key, "2026-06-11") == 3
    # New day → counter resets to 1
    assert usage_limits._local_incr(key, "2026-06-12") == 1


def test_seconds_until_midnight_is_bounded():
    secs = usage_limits._seconds_until_midnight("America/Argentina/Buenos_Aires")
    assert 60 <= secs <= 86400


def test_tz_falls_back_on_bad_zone():
    # An invalid tz name must not raise — it falls back to the default zone.
    assert usage_limits._today_str("Not/AZone")  # returns a YYYY-MM-DD string


# ── Daily-cap message ───────────────────────────────────────────────────────────

def test_daily_cap_message_includes_agency():
    msg = engine._daily_cap_message("Inmobiliaria Oberá")
    assert "Inmobiliaria Oberá" in msg
    assert "límite" in msg.lower()


def test_daily_cap_message_without_agency():
    msg = engine._daily_cap_message("")
    assert "asesor" in msg.lower()


# ── Belief field round-trip ─────────────────────────────────────────────────────

def test_offtopic_abuse_count_survives_serialization():
    b = BeliefStateV5(session_id="s1")
    b.offtopic_abuse_count = 4
    restored = deserialize_v5(serialize_v5(b), "s1")
    assert restored.offtopic_abuse_count == 4


def test_offtopic_abuse_count_defaults_zero_on_legacy_data():
    # v5 belief serialized without the field (legacy) deserializes to 0.
    import json
    raw = json.dumps({"schema_version": 5, "session_id": "s2"})
    restored = deserialize_v5(raw, "s2")
    assert restored.offtopic_abuse_count == 0
