"""Per-tenant presentation profile (V3 multi-tenancy).

Resolves everything that used to be hardcoded to Oberá — agency name, bot name,
city/region, operating zones, timezone and business hours — from the ``Tenant`` row
(+ its FAQ) so the bot can serve inmobiliarias anywhere in the country.

Sourcing (all per-tenant, with graceful fallback):
- agency_name : Tenant.display_name
- bot_name    : Tenant.branding["bot_name"]
- city/region/country : Tenant.branding["city"|"region"|"country"]
- zones       : Tenant.zones (JSON list, or dict with "neighborhoods")
- timezone + hours : load_tenant_hours() (FAQ → Tenant.business_hours → defaults)

Legacy fallback: the original single-tenant deployment (the default tenant) had no
branding/zones configured, so when those are absent **and** the tenant is the default
tenant we fall back to the historical Oberá values — existing behavior is preserved.
New tenants simply omit what they haven't configured yet.

Cached per-tenant with a short TTL so the policy prompt stays byte-stable within a
session (OpenAI prompt-cache friendly) without a DB hit every turn.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

from loguru import logger

# Historical defaults for the original Oberá deployment (applied only to the default tenant).
_LEGACY_CITY = "Oberá"
_LEGACY_REGION = "Misiones"
_LEGACY_COUNTRY = "Argentina"
_DEFAULT_BOT_NAME = "el asistente virtual"

_PROFILE_TTL = 300.0
_profile_cache: dict[str, tuple["TenantProfile", float]] = {}


@dataclass(frozen=True)
class TenantProfile:
    """Resolved, presentation-ready config for one inmobiliaria (tenant)."""
    tenant_id: UUID | None
    agency_name: str
    bot_name: str
    city: str
    region: str
    country: str
    zones: list[str]
    timezone: str
    hours_text: str


def bust_profile_cache() -> None:
    """Invalidate the profile cache (call after tenant/FAQ edits)."""
    _profile_cache.clear()


def _legacy_zone_names() -> list[str]:
    """Default neighborhood list for the original Oberá tenant (from ZONE_PATTERNS)."""
    try:
        from app.core.state_transitioner import ZONE_PATTERNS
        return [name for _, name in ZONE_PATTERNS]
    except Exception:
        return []


def _coerce_zone_list(zones) -> list[str]:
    """Accept Tenant.zones as a JSON list or a dict ({"neighborhoods": [...]})."""
    if isinstance(zones, list):
        return [str(z) for z in zones if z]
    if isinstance(zones, dict):
        nb = zones.get("neighborhoods") or zones.get("zonas") or zones.get("zones")
        if isinstance(nb, list):
            return [str(z) for z in nb if z]
    return []


async def load_tenant_profile(tenant_id: UUID | None) -> TenantProfile:
    """Load (and cache) the presentation profile for ``tenant_id``. Never raises."""
    cache_key = str(tenant_id)
    now = time.monotonic()
    cached = _profile_cache.get(cache_key)
    if cached and (now - cached[1]) < _PROFILE_TTL:
        return cached[0]

    profile = await _build_profile(tenant_id)
    _profile_cache[cache_key] = (profile, now)
    return profile


async def _build_profile(tenant_id: UUID | None) -> TenantProfile:
    from app.core.tenancy import default_tenant_id
    from app.routers.v3.scheduling.utils import describe_hours, load_tenant_hours

    is_default = tenant_id is None or tenant_id == default_tenant_id()

    tenant = None
    if tenant_id is not None:
        try:
            from app.services.tenant_service import get_tenant
            tenant = await get_tenant(tenant_id)
        except Exception as exc:
            logger.debug("[tenant_profile] get_tenant failed: {}", exc)

    branding = (getattr(tenant, "branding", None) or {}) if tenant else {}

    def _b(key: str) -> str | None:
        val = branding.get(key) if isinstance(branding, dict) else None
        return str(val).strip() if val else None

    agency_name = (getattr(tenant, "display_name", None) or "").strip() or (
        "la inmobiliaria"
    )
    bot_name = _b("bot_name") or _DEFAULT_BOT_NAME
    city = _b("city") or (_LEGACY_CITY if is_default else "")
    region = _b("region") or (_LEGACY_REGION if is_default else "")
    country = _b("country") or _LEGACY_COUNTRY

    zones = _coerce_zone_list(getattr(tenant, "zones", None))
    if not zones and is_default:
        zones = _legacy_zone_names()

    # Hours + timezone (FAQ → business_hours → defaults), rendered to text.
    try:
        windows, tz_str = await load_tenant_hours(tenant_id)
        hours_text = describe_hours(windows)
    except Exception as exc:
        logger.debug("[tenant_profile] load_tenant_hours failed: {}", exc)
        from app.routers.v3.scheduling.utils import DEFAULT_TZ
        tz_str, hours_text = DEFAULT_TZ, describe_hours({})

    return TenantProfile(
        tenant_id=tenant_id,
        agency_name=agency_name,
        bot_name=bot_name,
        city=city,
        region=region,
        country=country,
        zones=zones,
        timezone=tz_str,
        hours_text=hours_text,
    )
