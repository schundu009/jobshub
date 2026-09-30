"""
Plan gating for Auto Apply.

Paid status comes from the user's cariara.com plan (services.cariara_identity).
ApplyPreference.plan_override
("pro"/"paid" or "free") takes precedence; it is ops-set only, for comp
accounts and local development. Admins (middleware.auth.ADMIN_ROLES) count
as paid.
"""
from dataclasses import dataclass
from typing import Optional

from services.apply.constants import PAID_DAILY_CAP_MAX

PAID_OVERRIDES = {"pro", "paid", "quarterly_pro", "premium"}
FREE_OVERRIDES = {"free", "none"}


@dataclass
class PlanInfo:
    plan_ok: bool
    plan_type: str
    daily_cap_max: int


def resolve_plan(user, override: Optional[str] = None) -> PlanInfo:
    """Paid / free for Auto Apply."""
    value = (override or "").strip().lower()
    if value in PAID_OVERRIDES:
        return PlanInfo(True, value, PAID_DAILY_CAP_MAX)
    if value in FREE_OVERRIDES:
        return PlanInfo(False, "free", 0)

    # Admins run the product; they aren't customers. (A "free" override above
    # still wins, so the free experience can be tested from an admin account.)
    from middleware.auth import is_admin
    if is_admin(user):
        return PlanInfo(True, "admin", PAID_DAILY_CAP_MAX)

    # A paid cariara.com plan (services.cariara_identity) counts as paid.
    from services.cariara_identity import cariara_paid_plan
    cariara_plan = cariara_paid_plan(user)
    if cariara_plan:
        return PlanInfo(True, cariara_plan, PAID_DAILY_CAP_MAX)

    return PlanInfo(False, "free", 0)
