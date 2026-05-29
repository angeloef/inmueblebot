"""Current-session contact identity (Meta BSUID migration).

A per-turn ContextVar holding the *session* identity derived from the webhook —
never from conversation content. Tools that persist a lead (e.g. schedule_visit)
read this to key the user, so identity can never be spoofed by what the user types.

Set once at the start of each turn (process_turn_v2); read anywhere downstream in
the same async task. BSUID is the durable key (phone is a fallback/contact and may
disappear from webhooks once WhatsApp usernames roll out). See [[meta-bsuid-identity-migration]].
"""

from contextvars import ContextVar
from typing import Optional, TypedDict


class Contact(TypedDict):
    phone: Optional[str]
    bsuid: Optional[str]


_current_contact: ContextVar[Contact] = ContextVar(
    "current_contact", default={"phone": None, "bsuid": None}
)


def set_current_contact(phone: Optional[str], bsuid: Optional[str] = None) -> None:
    """Record the session identity for the current turn. Call at turn entry."""
    _current_contact.set({"phone": phone or None, "bsuid": bsuid or None})


def get_current_contact() -> Contact:
    """Return the current turn's session identity ({'phone', 'bsuid'})."""
    return _current_contact.get()
