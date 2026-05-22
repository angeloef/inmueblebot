"""
v2.0 Typed Tool Results.

Every tool returns a typed dataclass instead of a raw string.
The orchestrator serializes these to structured JSON for the LLM context,
and extracts the user_message field for the final response.

This eliminates Plan B injection — the LLM receives structured data,
not formatted text to parse.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Literal
import json


# ── Shared property summary ──────────────────────────────────────────────

@dataclass
class PropertySummary:
    """Lightweight property info for search results."""
    id: str
    title: str
    price: int
    currency: str = "ARS"
    location: str = ""
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_m2: Optional[int] = None
    property_type: str = ""
    operation_type: str = ""


# ── Tool-specific result types ───────────────────────────────────────────

@dataclass
class SearchResult:
    """Result from search_properties or refine_search."""
    properties: list[PropertySummary] = field(default_factory=list)
    total_count: int = 0
    criteria_applied: dict[str, Any] = field(default_factory=dict)
    fallback_applied: bool = False
    user_message: str = ""  # pre-formatted Spanish text for the user

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class DetailResult:
    """Result from get_property_details."""
    property: Optional[PropertySummary] = None
    description: str = ""
    image_count: int = 0
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class ScheduleResult:
    """Result from schedule_visit."""
    status: Literal["confirmed", "needs_date", "needs_time", "needs_name", "rejected"] = "needs_date"
    appointment_id: Optional[str] = None
    property_title: str = ""
    property_id: str = ""
    date: Optional[str] = None
    time: Optional[str] = None
    missing_field: Optional[str] = None  # "date", "time", "name"
    rejection_reason: Optional[str] = None
    alternatives: list[str] = field(default_factory=list)
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class AppointmentListResult:
    """Result from get_my_appointments."""
    appointments: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class AppointmentActionResult:
    """Result from reschedule_appointment or cancel_appointment."""
    action: Literal["rescheduled", "cancelled"] = "cancelled"
    success: bool = False
    appointment_id: Optional[str] = None
    property_title: str = ""
    new_date: Optional[str] = None
    new_time: Optional[str] = None
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class ImageResult:
    """Result from get_property_images."""
    property_id: str = ""
    image_urls: list[str] = field(default_factory=list)
    count: int = 0
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class FAQResult:
    """Result from get_faq_answer."""
    question: str = ""
    answer: str = ""
    found: bool = False
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)


@dataclass
class SimpleResult:
    """Generic confirmation/status result (handoff, preferences, etc.)."""
    action: str = ""  # e.g. "handoff_initiated", "preferences_updated"
    success: bool = True
    details: dict[str, Any] = field(default_factory=dict)
    user_message: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False)
