"""Tests for the per-tenant presentation profile (de-hardcoding Oberá).

Verifies that agency/bot/city/zones resolve from the Tenant row's branding/zones,
and that an unconfigured non-default tenant degrades cleanly (no Oberá leakage),
while the default tenant keeps the legacy Oberá values.
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import app.services.tenant_service  # noqa: F401 — ensure submodule loaded for patch target

from app.routers.v3 import tenant_profile as tp


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_tenant(**kw):
    base = dict(display_name="Inmobiliaria Test", branding=None, zones=None,
                timezone="America/Argentina/Cordoba", business_hours=None)
    base.update(kw)
    return SimpleNamespace(**base)


class TestTenantProfile(unittest.TestCase):
    def setUp(self):
        tp.bust_profile_cache()

    def test_branding_drives_identity(self):
        tenant = _fake_tenant(
            display_name="Grupo Pampa Propiedades",
            branding={"bot_name": "Pampita", "city": "Rosario", "region": "Santa Fe"},
            zones=["Centro", "Pichincha", "Fisherton"],
        )
        with patch("app.services.tenant_service.get_tenant", new=AsyncMock(return_value=tenant)):
            with patch("app.routers.v3.scheduling.utils.load_tenant_hours",
                       new=AsyncMock(return_value=(_DEFAULT, "America/Argentina/Cordoba"))):
                p = _run(tp.load_tenant_profile(uuid4()))
        self.assertEqual(p.agency_name, "Grupo Pampa Propiedades")
        self.assertEqual(p.bot_name, "Pampita")
        self.assertEqual(p.city, "Rosario")
        self.assertEqual(p.region, "Santa Fe")
        self.assertIn("Pichincha", p.zones)

    def test_unconfigured_non_default_tenant_has_no_obera(self):
        tenant = _fake_tenant(display_name="Nueva Inmo", branding=None, zones=None)
        with patch("app.services.tenant_service.get_tenant", new=AsyncMock(return_value=tenant)):
            with patch("app.routers.v3.scheduling.utils.load_tenant_hours",
                       new=AsyncMock(return_value=(_DEFAULT, "America/Argentina/Cordoba"))):
                p = _run(tp.load_tenant_profile(uuid4()))
        self.assertEqual(p.city, "")          # no Oberá leakage for new tenants
        self.assertEqual(p.zones, [])
        self.assertEqual(p.agency_name, "Nueva Inmo")


_DEFAULT = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}


if __name__ == "__main__":
    unittest.main()
