"""Admins get Auto Apply without a subscription (services/apply/plans.py)."""
from types import SimpleNamespace

import pytest

from services.apply import plans


@pytest.fixture(autouse=True)
def not_subscribed(monkeypatch):
    monkeypatch.setattr(plans, "verify_subscription_sync", lambda user_id: {"hasAccess": False, "planType": "free"})


@pytest.mark.parametrize("role", ["admin", "Administrator", "developer", "manager"])
def test_admin_roles_are_paid(role):
    info = plans.resolve_plan(SimpleNamespace(id=1, role=role))
    assert info.plan_ok and info.plan_type == "admin" and info.daily_cap_max > 0


def test_regular_user_without_subscription_is_free():
    assert not plans.resolve_plan(SimpleNamespace(id=1, role="user")).plan_ok


def test_free_override_still_applies_to_admins():
    assert not plans.resolve_plan(SimpleNamespace(id=1, role="admin"), override="free").plan_ok
