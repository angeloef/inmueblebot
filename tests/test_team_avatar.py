"""Unit tests for avatar propagation in team_service (plan 31)."""
from types import SimpleNamespace

import pytest


def _make_acc(avatar_photo=None):
    """Minimal TenantAccount stand-in."""
    from datetime import datetime, timezone
    return SimpleNamespace(
        id="acc-1", email="a@b.com", full_name="Alice",
        avatar_photo=avatar_photo, role="owner",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_account_member_propagates_avatar_photo():
    from app.services.team_service import _account_member
    acc = _make_acc(avatar_photo="data:image/jpeg;base64,abc123")
    m = _account_member(acc, role="owner", branch_name=None)
    assert m.photo_url == "data:image/jpeg;base64,abc123"


def test_account_member_no_photo_is_none():
    from app.services.team_service import _account_member
    acc = _make_acc(avatar_photo=None)
    m = _account_member(acc, role="admin", branch_name=None)
    assert m.photo_url is None
