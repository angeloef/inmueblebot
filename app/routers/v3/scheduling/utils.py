"""Scheduling utilities — date/time parsing + business-hours logic.

Pure functions + one async DB call (load_tenant_hours). No LLM calls.
All functions are fail-soft: they wrap their bodies and degrade to safe defaults
rather than raising.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_TZ = "America/Argentina/Cordoba"

# Mon(0)–Fri(4) 09:00–18:00, Sat(5) 09:00–13:00, Sun(6) closed (absent key).
_DEFAULT_WINDOWS: dict[int, tuple[int, int]] = {
    0: (9, 18),
    1: (9, 18),
    2: (9, 18),
    3: (9, 18),
    4: (9, 18),
    5: (9, 13),
}

# ── Day-name maps ─────────────────────────────────────────────────────────────

# EN short → weekday int (Mon=0 … Sun=6)
_EN_DAYS: dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}
# ES short/full → weekday int
_ES_DAYS: dict[str, int] = {
    "lun": 0, "mar": 1, "mié": 2, "mie": 2,
    "jue": 3, "vie": 4, "sáb": 5, "sab": 5, "dom": 6,
}

# Regex for "HH:MM" time in a business-hours clause
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

# Regex for a day range like "Mon-Fri" or "Lun-Vie"
_DAY_RANGE_RE = re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ]+)(?:-([A-Za-záéíóúüñÁÉÍÓÚÜÑ]+))?")


def _parse_day_token(token: str) -> int | None:
    """Map a 3-char EN or ES day abbreviation to weekday int (0=Mon). None on failure."""
    t = token.lower().strip()
    if t in _EN_DAYS:
        return _EN_DAYS[t]
    if t in _ES_DAYS:
        return _ES_DAYS[t]
    # Try 3-char prefix
    for k, v in _EN_DAYS.items():
        if t.startswith(k):
            return v
    for k, v in _ES_DAYS.items():
        if t.startswith(k):
            return v
    return None


def parse_business_hours(text: str | None) -> dict[int, tuple[int, int]] | None:
    """Parse a business-hours string into a weekday→(open_h, close_h) dict.

    Accepts comma-separated clauses like:
        "Mon-Fri 09:00-18:00, Sat 09:00-13:00"
        "Lun-Vie 09:00-18:00, Sáb 09:00-13:00"
    Day tokens: EN (Mon..Sun) or ES (Lun..Dom, Sáb).

    Returns None if text is None/empty or no valid clauses are parsed.
    """
    if not text:
        return None
    result: dict[int, tuple[int, int]] = {}
    try:
        clauses = [c.strip() for c in text.split(",") if c.strip()]
        for clause in clauses:
            # Extract two HH:MM times
            times = _TIME_RE.findall(clause)
            if len(times) < 2:
                continue
            open_h = int(times[0][0])
            close_h = int(times[1][0])
            if not (0 <= open_h <= 23 and 0 <= close_h <= 23):
                continue
            # Extract day range
            # Remove time part to isolate day portion
            day_part = _TIME_RE.sub("", clause).replace("-", " - ")
            dm = re.search(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,})\s*(?:-\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ]{2,}))?", day_part)
            if not dm:
                continue
            start_day = _parse_day_token(dm.group(1))
            if start_day is None:
                continue
            end_day = _parse_day_token(dm.group(2)) if dm.group(2) else start_day
            if end_day is None:
                end_day = start_day
            # Build range (wrapping from Sat(5) back, but we don't expect Sun-Fri)
            if end_day >= start_day:
                for d in range(start_day, end_day + 1):
                    result[d] = (open_h, close_h)
            else:
                # Wrap-around range (e.g. Sat–Mon). Unlikely but safe.
                for d in list(range(start_day, 7)) + list(range(0, end_day + 1)):
                    result[d] = (open_h, close_h)
    except Exception as exc:
        logger.debug("[scheduling.utils] parse_business_hours error: {}", exc)
        return None
    return result if result else None


def is_within_business_hours(
    dt: datetime, windows: dict[int, tuple[int, int]]
) -> bool:
    """Return True if dt falls within the open window for its weekday.

    Sunday (weekday 6) closed if not in windows.
    Never raises — on any exception returns True (fail-open).
    """
    try:
        wd = dt.weekday()
        if wd not in windows:
            return False
        open_h, close_h = windows[wd]
        return open_h <= dt.hour < close_h
    except Exception:
        return True


async def load_tenant_hours(
    tenant_id,
) -> tuple[dict[int, tuple[int, int]], str]:
    """Load business-hours windows and IANA timezone for a tenant.

    3-tier degradation (never raises):
    1. Tenant found + business_hours parses → parsed windows + Tenant.timezone
    2. Tenant found, business_hours null/malformed → DEFAULT_WINDOWS + Tenant.timezone
    3. get_tenant None or tz invalid → DEFAULT_WINDOWS + DEFAULT_TZ
    """
    try:
        from app.services.tenant_service import get_tenant

        if tenant_id is None:
            return _DEFAULT_WINDOWS.copy(), DEFAULT_TZ

        tenant = await get_tenant(tenant_id)
        if tenant is None:
            return _DEFAULT_WINDOWS.copy(), DEFAULT_TZ

        # Validate timezone
        tz_str = tenant.timezone or DEFAULT_TZ
        try:
            import zoneinfo
            zoneinfo.ZoneInfo(tz_str)
        except Exception:
            tz_str = DEFAULT_TZ

        # Parse business_hours text
        windows = parse_business_hours(tenant.business_hours)
        if windows is None:
            windows = _DEFAULT_WINDOWS.copy()

        return windows, tz_str
    except Exception as exc:
        logger.debug("[scheduling.utils] load_tenant_hours error: {}", exc)
        return _DEFAULT_WINDOWS.copy(), DEFAULT_TZ


async def parse_day_time_for_tenant(
    day_str: str | None,
    time_str: str | None,
    tenant_id,
) -> Optional[datetime]:
    """Parse day/time strings into a timezone-aware datetime for the given tenant.

    Uses the same chain as schedule_visit.py:
      1. hybrid date_parser.parse (app.core.hybrid.date.date_parser)
      2. Fallback: _parse_simple_date from schedule_visit

    Localizes result to tenant timezone. Rolls forward past datetimes by +7 days.
    Returns None if unparseable. Never raises.
    """
    try:
        if not day_str:
            return None

        from app.utils.date_parser import get_argentina_now

        now = get_argentina_now()
        combined = f"{day_str} {time_str or ''}".strip()

        parsed_dt: datetime | None = None

        # Path 1: hybrid date_parser (same as schedule_visit.py lines 59-66)
        try:
            from app.core.hybrid.date import date_parser as hybrid_date_parser

            parse_ctx = {
                "date_str": day_str,
                "time_str": time_str or "",
                "reference_dt": now,
            }
            date_result = await hybrid_date_parser.parse(combined, parse_ctx)
            parsed_dt = date_result.value
        except Exception:
            pass

        # Path 2: _parse_simple_date fallback
        if not parsed_dt:
            try:
                from app.tools.v2.schedule_visit import _parse_simple_date

                parsed_dt = _parse_simple_date(day_str, time_str or "", now)
            except Exception:
                pass

        if not parsed_dt:
            return None

        # Localize to tenant timezone
        _, tz_str = await load_tenant_hours(tenant_id)
        try:
            import zoneinfo

            tenant_tz = zoneinfo.ZoneInfo(tz_str)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=tenant_tz)
            else:
                parsed_dt = parsed_dt.astimezone(tenant_tz)
        except Exception:
            pass

        # Roll forward if in the past
        try:
            now_aware = now if now.tzinfo else now.replace(
                tzinfo=__import__("zoneinfo").ZoneInfo(DEFAULT_TZ)
            )
            if parsed_dt.tzinfo is None:
                compare_dt = parsed_dt
                compare_now = now.replace(tzinfo=None) if now.tzinfo else now
            else:
                compare_dt = parsed_dt
                compare_now = now_aware
            if compare_dt <= compare_now:
                parsed_dt = parsed_dt + timedelta(days=7)
        except Exception:
            pass

        return parsed_dt
    except Exception as exc:
        logger.debug("[scheduling.utils] parse_day_time_for_tenant error: {}", exc)
        return None
