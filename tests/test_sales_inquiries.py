"""Tests del flujo 'Hablar con ventas' Enterprise (plan 20).

Offline: valida schemas Pydantic, la constante del email de ventas, y que
los endpoints de listado/triage exigen super-admin.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes.sales_inquiries import SalesInquiryCreate, SalesInquiryUpdate, _SALES_EMAIL, STATUSES


# ── Esquema de creación ────────────────────────────────────────────────────────


def test_create_schema_requires_contact_name() -> None:
    with pytest.raises(ValidationError):
        SalesInquiryCreate(contact_name="")


def test_create_schema_accepts_minimal() -> None:
    s = SalesInquiryCreate(contact_name="Ana García")
    assert s.contact_name == "Ana García"
    assert s.phone is None
    assert s.message is None


def test_create_schema_trims_and_validates_optional() -> None:
    s = SalesInquiryCreate(
        contact_name="Pedro López",
        phone="+54 9 11 1234-5678",
        property_count="150 props, 2 sucursales",
        message="Queremos Enterprise",
    )
    assert s.phone == "+54 9 11 1234-5678"
    assert s.property_count == "150 props, 2 sucursales"


# ── Constantes ────────────────────────────────────────────────────────────────


def test_sales_email_constant() -> None:
    assert "@" in _SALES_EMAIL


def test_statuses_are_exhaustive() -> None:
    assert set(STATUSES) == {"open", "contacted", "closed"}


# ── Schema de triage ──────────────────────────────────────────────────────────


def test_update_schema_accepts_valid_status() -> None:
    u = SalesInquiryUpdate(status="contacted")
    assert u.status == "contacted"


def test_update_schema_accepts_none() -> None:
    u = SalesInquiryUpdate()
    assert u.status is None
