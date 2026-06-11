"""Scheduling robustness — date/name helpers + the booking-confirmation surfacing.

Covers the manual-test-6 fixes:
  - Past date rolled forward must be detectable + informed (not silent).
  - Weekday-vs-explicit-date mismatch is caught.
  - Bare hour 1–7 → PM (never 03:00); unparseable time → None (no silent 16:00).
  - "name" that is really a slot value is rejected.
  - On a SUCCESSFUL booking, the engine surfaces the real schedule_visit
    confirmation (date/time/address) instead of the engine's generic placeholder.

Offline: no DB / LLM / network. Engine test is async (suite runs mode=auto).
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytz

from app.tools.v2.schedule_visit import (
    _named_weekday,
    _explicit_date_in,
    _looks_like_slot_value,
    _format_day_date,
    _is_past,
    _parse_simple_date,
)
from app.routers.v3 import engine
from app.routers.v3.schema import TurnOutput, BeliefDelta

_AR = pytz.timezone("America/Argentina/Buenos_Aires")


# ── date helpers ──────────────────────────────────────────────────────────────

def test_named_weekday():
    assert _named_weekday("el lunes a las 3") == 0
    assert _named_weekday("sábado") == 5
    assert _named_weekday("08/06") is None


def test_explicit_date_in():
    now = datetime(2026, 6, 9, tzinfo=_AR)
    assert _explicit_date_in("lunes 08/06", now) == date(2026, 6, 8)
    assert _explicit_date_in("el 25/12/2026", now) == date(2026, 12, 25)
    assert _explicit_date_in("mañana", now) is None
    assert _explicit_date_in("99/99", now) is None  # invalid → None


def test_weekday_vs_date_mismatch_is_detectable():
    now = datetime(2026, 6, 9, tzinfo=_AR)
    # 2026-06-09 is a Tuesday (weekday 1); "lunes" is 0 → mismatch.
    d = _explicit_date_in("lunes 09/06", now)
    assert d is not None and d.weekday() != _named_weekday("lunes 09/06")


def test_is_past_tz_safe():
    now = datetime(2026, 6, 9, 12, 0, tzinfo=_AR)
    assert _is_past(datetime(2026, 6, 8, 12, 0, tzinfo=_AR), now) is True
    assert _is_past(datetime(2026, 6, 10, 12, 0, tzinfo=_AR), now) is False
    # naive vs aware must not raise
    assert _is_past(datetime(2026, 6, 8, 12, 0), now) is True


def test_format_day_date():
    assert _format_day_date(datetime(2026, 6, 15)) == "lunes 15/06"


# ── name validation ───────────────────────────────────────────────────────────

def test_looks_like_slot_value():
    assert _looks_like_slot_value("el viernes") is True
    assert _looks_like_slot_value("tarde") is True
    assert _looks_like_slot_value("15hs") is True
    assert _looks_like_slot_value("sí") is True
    assert _looks_like_slot_value("Marcos") is False
    assert _looks_like_slot_value("Juan Pérez") is False
    assert _looks_like_slot_value("") is False


# ── time parsing ──────────────────────────────────────────────────────────────

def test_bare_hour_1_to_7_is_pm():
    now = datetime(2026, 6, 9, 9, 0, tzinfo=_AR)
    dt = _parse_simple_date("lunes", "3", now)
    assert dt is not None and dt.hour == 15  # 3 → 15:00, not 03:00


def test_explicit_numeric_time_kept():
    now = datetime(2026, 6, 9, 9, 0, tzinfo=_AR)
    dt = _parse_simple_date("lunes", "10", now)
    assert dt is not None and dt.hour == 10  # 10 stays 10:00 (not in 1–7)


def test_unparseable_time_returns_none():
    now = datetime(2026, 6, 9, 9, 0, tzinfo=_AR)
    # No named period, no digits → cannot infer a time → None (no silent 16:00).
    assert _parse_simple_date("lunes", "cuando puedas", now) is None


def test_named_period_time():
    now = datetime(2026, 6, 9, 9, 0, tzinfo=_AR)
    dt = _parse_simple_date("lunes", "por la tarde", now)
    assert dt is not None and dt.hour == 16


# ── engine: surface the real confirmation on success ──────────────────────────

def _turn(action="book_step"):
    return TurnOutput(
        belief_delta=BeliefDelta(),
        intent="scheduling",
        action=action,
        tool_calls=[],
        selected_property_id=None,
        missing_slot=None,
        response_plan=[{"type": "text", "content": "Listo, agendo tu visita."}],
        confidence=0.9,
    )


def _belief():
    return SimpleNamespace(
        selected_property_id=40, search_criteria={}, active_intents=set(),
    )


_CONFIRMATION = (
    "📅 *¡Cita Agendada!*\n\n📆 *Fecha:* 15/06/2026\n⏰ *Hora:* 15:00\n"
    "🏠 *Propiedad:* Casa Centro\n📍 *Dirección:* Av. Sarmiento 744"
    "\n\n<!--CONFIRMED:2026-06-15 15:00-->"
)


async def test_booking_success_surfaces_real_confirmation_not_placeholder():
    """On a confirmed booking, the user must get the date/time/address confirmation
    from schedule_visit — NOT the engine's generic response_plan placeholder."""
    text, _rich, _source = await engine._assemble_response(
        _turn("book_step"),
        _belief(),
        tool_results=[_CONFIRMATION],
        any_ran=True,
        tenant_id=None,
        booking_succeeded=True,
        tools_used=["schedule_visit"],
    )
    assert "15/06/2026" in text
    assert "Av. Sarmiento 744" in text
    assert "Listo, agendo tu visita" not in text  # placeholder discarded
    assert "<!--CONFIRMED:" not in text  # marker stripped


async def test_booking_failure_still_discards_fake_confirmation():
    """Regression guard: when booking did NOT succeed, never surface a confirmation."""
    text, _rich, _source = await engine._assemble_response(
        _turn("book_step"),
        _belief(),
        tool_results=["Ese horario ya está reservado. ¿Qué otro horario te conviene?"],
        any_ran=True,
        tenant_id=None,
        booking_succeeded=False,
        tools_used=["schedule_visit"],
    )
    assert "reservado" in text
    assert "Cita Agendada" not in text
