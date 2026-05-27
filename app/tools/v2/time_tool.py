"""Get current time tool."""

from datetime import datetime, timezone
from typing import Any


def get_time() -> str:
    """Return the current date and time in Argentina timezone (UTC-3)."""
    now = datetime.now(timezone.utc)
    # Argentina is UTC-3
    from datetime import timedelta

    arg_time = now - timedelta(hours=3)
    return arg_time.strftime("%A %d de %B de %Y, %H:%M:%S (ART)")
