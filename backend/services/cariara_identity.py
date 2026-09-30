"""
Sign-in from cariara.com (the copilot app) on the jobportal API.

How cariara.com authenticates (copilot repo, apps/api = "copilot-prep"):
- Google sign-in sets an httpOnly session cookie on cariara.com. The React app
  calls GET /api/v1/auth/me (Vercel forwards it to copilot-prep) and receives
  an ``access_token``: an HS256 JWT (claims sub, email, name, picture,
  type="access", gen, exp; iss/aud when AUTH_ISSUER is set) with a 30-day life.
  The app keeps it in memory (utils/tokenStore) and sends
  ``Authorization: Bearer <token>`` to every backend.
- GET {copilot-prep}/api/v1/auth/me with that bearer returns
  ``{authenticated, access_token, user: {id, email, name, picture, is_admin, ...}}``
  and 401 for a bad, expired or revoked (token_generation) token.
- GET {copilot-prep}/api/v1/billing/subscription returns
  ``{plan, plan_type, status, ...}``; paid = plan_type in PAID_PLAN_TYPES
  (byok, platform, team, lifetime) with status "active" (trialing is stored as
  active). Copilot's admin emails get plan_type "lifetime".

Jobportal never holds cariara's signing secret: a token is verified by asking
copilot-prep who it belongs to (3 s timeout), and the answer is cached for
``cariara_cache_ttl_seconds`` keyed by sha256(token) (Redis, with a small
in-process fallback). Unreachable copilot fails closed (CariaraUnavailable).

Mapping: the verified email (lowercased) finds or creates the jobportal User.
Copilot's ``user.id`` is the token's ``sub`` and is not stable for tokens
minted before sign-in moved to cariara.com, so email is the key and
``cariara_user_id`` is informational. A cariara token never changes a user's
``role``: jobportal's role is the only source of admin rights (a cariara admin
is not a jobportal admin unless their jobportal account already is).
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from jose import jwt
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models import User
from services.redis_service import redis_service

logger = logging.getLogger(__name__)

CACHE_PREFIX = "cariara:tok:"
IDENTITY_SOURCE = "cariara"
# Attribute set on the User instance for the current request.
REQUEST_ATTR = "cariara_identity"
# Skip rewriting an unchanged stored plan more often than this.
PLAN_WRITE_INTERVAL = timedelta(minutes=5)


class CariaraUnavailable(Exception):
    """copilot-prep could not answer (timeout, 5xx, network). Callers fail closed."""


@dataclass
class CariaraIdentity:
    cariara_user_id: Optional[str]
    email: str
    name: Optional[str]
    plan: str  # plan_type as reported, "free" when none, "unknown" when the check failed
    plan_status: Optional[str]
    paid: bool
    plan_known: bool
    cariara_admin: bool

    @property
    def effective_plan(self) -> str:
        """What we store on the user: the plan_type when paid, else "free"."""
        return self.plan if self.paid else "free"


# --------------------------------------------------------------------------- cache

_local_cache: Dict[str, tuple] = {}
_local_lock = threading.Lock()
_LOCAL_MAX = 2000


def _cache_key(token: str) -> str:
    return CACHE_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[dict]:
    value = redis_service.cache_get(key)
    if value is not None:
        return value
    with _local_lock:
        hit = _local_cache.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
        _local_cache.pop(key, None)
    return None


def _cache_set(key: str, value: dict, ttl: int) -> None:
    ttl = max(1, int(ttl))
    redis_service.cache_set(key, value, ttl_seconds=ttl)
    with _local_lock:
        if len(_local_cache) >= _LOCAL_MAX:
            _local_cache.clear()
        _local_cache[key] = (value, time.monotonic() + ttl)


def clear_local_cache() -> None:
    with _local_lock:
        _local_cache.clear()


# --------------------------------------------------------------------------- verification

def _unverified_claims(token: str) -> Optional[dict]:
    """Cheap shape check before any network call; the claims are NOT trusted."""
    if not token or token.count(".") != 2 or len(token) > 4096:
        return None
    try:
        claims = jwt.get_unverified_claims(token)
    except Exception:
        return None
    if not isinstance(claims, dict) or not claims.get("email"):
        return None
    if claims.get("type", "access") != "access":
        return None
    if "jti" in claims and "role" in claims:
        # jobportal's own token shape (utils/security.create_access_token) that
        # already failed jobportal verification: never forward it to cariara.
        return None
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp <= time.time():
        return None
    return claims


def looks_like_cariara_token(token: str) -> bool:
    return bool(settings.cariara_auth_enabled and _unverified_claims(token))


def _get(client: httpx.Client, path: str, token: str) -> httpx.Response:
    url = settings.cariara_api_url.rstrip("/") + path
    return client.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})


def _fetch_identity(token: str) -> Optional[dict]:
    """Ask copilot-prep. None = token rejected; raises CariaraUnavailable otherwise."""
    timeout = httpx.Timeout(settings.cariara_verify_timeout_seconds)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            me = _get(client, settings.cariara_me_path, token)
            if me.status_code in (401, 403):
                return None
            if me.status_code != 200:
                raise CariaraUnavailable(f"cariara /me returned {me.status_code}")
            try:
                body = me.json()
            except ValueError as exc:
                raise CariaraUnavailable("cariara /me returned non-JSON") from exc
            if not isinstance(body, dict) or body.get("authenticated") is False:
                return None
            user = body.get("user") if isinstance(body.get("user"), dict) else body
            email = str(user.get("email") or "").strip().lower()
            if not email or "@" not in email:
                return None

            plan, status, plan_known = "unknown", None, False
            try:
                sub = _get(client, settings.cariara_subscription_path, token)
                if sub.status_code == 200:
                    data = sub.json() or {}
                    nested = data.get("subscription") if isinstance(data.get("subscription"), dict) else {}
                    plan = str(data.get("plan_type") or data.get("plan") or nested.get("plan_type") or "free").lower()
                    status = str(data.get("status") or nested.get("status") or "").lower() or None
                    plan_known = True
                else:
                    logger.warning("cariara subscription check returned %s", sub.status_code)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("cariara subscription check failed: %s", exc)
    except httpx.HTTPError as exc:
        raise CariaraUnavailable(str(exc)) from exc

    paid = plan_known and plan in settings.cariara_paid_plans_set and status in (None, "active", "trialing")
    identity = CariaraIdentity(
        cariara_user_id=str(user["id"]) if user.get("id") not in (None, "") else None,
        email=email,
        name=(user.get("name") or None),
        plan=plan if plan_known else "unknown",
        plan_status=status,
        paid=bool(paid),
        plan_known=plan_known,
        cariara_admin=user.get("is_admin") is True,
    )
    return asdict(identity)


def verify_cariara_token(token: str) -> Optional[CariaraIdentity]:
    """Verified identity for a cariara.com token, or None if it isn't one / is rejected.

    Raises CariaraUnavailable when copilot-prep can't answer (fail closed).
    """
    if not settings.cariara_auth_enabled:
        return None
    claims = _unverified_claims(token)
    if not claims:
        return None

    key = _cache_key(token)
    cached = _cache_get(key)
    if cached is not None:
        return CariaraIdentity(**cached["identity"]) if cached.get("ok") else None

    ttl = settings.cariara_cache_ttl_seconds
    exp = claims.get("exp")
    if isinstance(exp, (int, float)):
        ttl = min(ttl, int(exp - time.time()))
    if ttl <= 0:
        return None

    identity = _fetch_identity(token)
    if identity is None:
        _cache_set(key, {"ok": False}, ttl)
        return None
    # A failed plan lookup is not cached for the full TTL, so paid status
    # recovers quickly once billing answers again.
    _cache_set(key, {"ok": True, "identity": identity}, ttl if identity["plan_known"] else min(ttl, 10))
    return CariaraIdentity(**identity)


# --------------------------------------------------------------------------- mapping

def _utcnow() -> datetime:
    """Naive UTC, like the other DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _set_cariara_user_id(db: Session, user: User, cariara_user_id: Optional[str]) -> None:
    if not cariara_user_id or user.cariara_user_id == cariara_user_id:
        return
    holder = db.query(User.id).filter(User.cariara_user_id == cariara_user_id, User.id != user.id).first()
    if holder:
        # copilot's id is the token's sub, not stable across its migrations;
        # email decides, so leave the other row's link alone.
        logger.warning("cariara_user_id %s already linked to user %s; not relinking to %s",
                       cariara_user_id, holder[0], user.id)
        return
    user.cariara_user_id = cariara_user_id


def _record_plan(user: User, identity: CariaraIdentity) -> bool:
    if not identity.plan_known:
        return False
    now = _utcnow()
    plan = identity.effective_plan
    checked = user.cariara_plan_checked_at
    if user.cariara_plan == plan and checked and now - checked < PLAN_WRITE_INTERVAL:
        return False
    user.cariara_plan = plan
    user.cariara_plan_checked_at = now
    return True


def link_or_create_user(db: Session, identity: CariaraIdentity) -> User:
    """The jobportal User for a verified cariara identity (found by email, else created).

    Never changes ``role``; new accounts are plain users.
    """
    email = identity.email.lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is None:
        user = User(
            email=email,
            name=(identity.name or email.split("@")[0])[:255],
            password_hash=None,
            is_email_verified=True,  # cariara.com sign-in is Google OAuth
            is_active=True,
            role="user",
            identity_source=IDENTITY_SOURCE,
        )
        _set_cariara_user_id(db, user, identity.cariara_user_id)
        _record_plan(user, identity)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # A parallel first request created the row; use that one.
            db.rollback()
            user = db.query(User).filter(func.lower(User.email) == email).first()
            if user is None:
                raise
        else:
            db.refresh(user)
            logger.info("Created jobportal user %s from cariara.com sign-in", user.id)
            return user

    changed = False
    if user.cariara_user_id != identity.cariara_user_id and identity.cariara_user_id:
        before = user.cariara_user_id
        _set_cariara_user_id(db, user, identity.cariara_user_id)
        changed = user.cariara_user_id != before
    changed = _record_plan(user, identity) or changed
    if changed:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.warning("Could not update cariara link for user %s", user.id)
    return user


def user_from_cariara_token(db: Session, token: str) -> Optional[User]:
    """Verify + map. None when the token isn't a valid cariara token.

    Raises CariaraUnavailable when copilot-prep can't be reached.
    """
    identity = verify_cariara_token(token)
    if identity is None:
        return None
    user = link_or_create_user(db, identity)
    setattr(user, REQUEST_ATTR, identity)
    return user


# --------------------------------------------------------------------------- plan

def cariara_paid_plan(user: Any) -> Optional[str]:
    """The cariara.com paid plan_type for this user, or None.

    Uses the identity verified on this request when present, else the stored
    plan if checked within cariara_plan_max_age_hours (Celery / no token).
    """
    identity = getattr(user, REQUEST_ATTR, None)
    if isinstance(identity, CariaraIdentity) and identity.plan_known:
        return identity.plan if identity.paid else None
    plan = getattr(user, "cariara_plan", None)
    checked = getattr(user, "cariara_plan_checked_at", None)
    if not plan or plan == "free" or not isinstance(checked, datetime):
        return None
    if plan not in settings.cariara_paid_plans_set:
        return None
    if _utcnow() - checked > timedelta(hours=settings.cariara_plan_max_age_hours):
        return None
    return plan
