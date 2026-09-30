"""
Plan gating for Auto Apply.

Paid status comes from capra-backend (services.subscription_service, the same
source as GET /api/auth/subscription-status). ApplyPreference.plan_override
("pro"/"paid" or "free") takes precedence; it is ops-set only, for comp
accounts and local development. Admins (middleware.auth.ADMIN_ROLES) count
as paid.
"""
import asyncio
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


def verify_subscription_sync(user_id: int) -> dict:
    """Run the async capra-backend check from sync code (routes run in a threadpool, tasks in Celery)."""
    from services.subscription_service import verify_subscription

    try:
        return asyncio.run(verify_subscription(user_id))
    except Exception:
        # Includes "called from a running event loop": fail closed.
        return {"hasAccess": False, "planType": "unknown"}


def resolve_plan(user, override: Optional[str] = None) -> PlanInfo:
    """Paid / free for Auto Apply. Fails closed (free) when the check errors."""
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

    result = verify_subscription_sync(user.id) or {}
    if result.get("hasAccess"):
        return PlanInfo(True, str(result.get("planType") or "pro"), PAID_DAILY_CAP_MAX)
    return PlanInfo(False, str(result.get("planType") or "free"), 0)
