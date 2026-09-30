"""
Authentication middleware and dependencies.

Provides FastAPI dependencies for protecting routes and getting current user.
Includes token blacklist checking for secure logout/revocation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

try:
    from database import get_db
    from models import User
    from utils.security import decode_token, as_utc
    from services.redis_service import redis_service
except ImportError:
    from database import get_db
    from models import User
    from utils.security import decode_token, as_utc
    from services.redis_service import redis_service

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _header_value(value) -> Optional[str]:
    """A Header() param's value; direct callers leave the FieldInfo default in place."""
    return value.strip() or None if isinstance(value, str) else None


def _check_account(user: User) -> User:
    if not user.is_active:
        raise _unauthorized("User account is disabled")
    if user.locked_until and as_utc(user.locked_until) > datetime.now(timezone.utc):
        raise _unauthorized("Account is temporarily locked")
    return user


def _user_from_cariara(token: str, db: Session) -> Optional[User]:
    """jobportal User for a cariara.com token (services/cariara_identity.py), or None."""
    from services.cariara_identity import CariaraUnavailable, user_from_cariara_token

    try:
        user = user_from_cariara_token(db, token)
    except CariaraUnavailable as exc:
        logger.warning("cariara.com sign-in could not be verified: %s", exc)
        # Fail closed, but say it's temporary so the client doesn't sign out.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="cariara.com sign-in could not be verified, try again shortly",
        )
    return _check_account(user) if user is not None else None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    x_cariara_token: Optional[str] = Header(None, alias="X-Cariara-Token"),
) -> User:
    """
    Dependency to get the current authenticated user.

    Accepts either a jobportal access token (Authorization: Bearer, checked
    first, unchanged behavior) or a cariara.com access token, sent as
    Authorization: Bearer <token> or X-Cariara-Token: <token>.
    """
    cariara_token = _header_value(x_cariara_token)
    if not credentials and not cariara_token:
        raise _unauthorized("Authentication required")

    token = credentials.credentials if credentials else None
    payload = decode_token(token) if token else None

    if not payload:
        # Not a jobportal token: try it (or X-Cariara-Token) as a cariara.com token.
        user = _user_from_cariara(cariara_token or token, db)
        if user is not None:
            return user
        raise _unauthorized("Invalid or expired token")

    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is blacklisted (for logout/revocation)
    jti = payload.get("jti")
    if jti and redis_service.is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user's tokens are globally blacklisted (force logout)
    user_id = int(payload.get("sub"))
    token_iat = payload.get("iat")
    if token_iat:
        blacklist_time = redis_service.get_user_blacklist_time(user_id)
        if blacklist_time and token_iat < blacklist_time:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired, please login again",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is locked
    if user.locked_until and as_utc(user.locked_until) > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is temporarily locked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user_detached(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    x_cariara_token: Optional[str] = Header(None, alias="X-Cariara-Token"),
) -> User:
    """
    Like get_current_user, but ends the session's transaction right after the
    lookup so the pooled DB connection goes back to the pool before the
    handler runs (a Session otherwise pins its connection until the request
    finishes).

    For handlers that do slow non-DB work (Celery/Redis inspection). The
    returned User is detached: plain column attributes (id, role, email, ...)
    work, lazy relationships do not.
    """
    user = get_current_user(credentials, db, x_cariara_token)
    db.expunge(user)
    db.rollback()
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    x_cariara_token: Optional[str] = Header(None, alias="X-Cariara-Token"),
) -> Optional[User]:
    """
    Dependency to optionally get the current user.

    Returns None if not authenticated (instead of raising exception).
    Useful for routes that work both authenticated and unauthenticated.
    """
    if not credentials and not _header_value(x_cariara_token):
        return None

    try:
        return get_current_user(credentials, db, x_cariara_token)
    except HTTPException:
        return None


# Roles with access to admin-only endpoints (mirrors ADMIN_ROLES in admin-app).
ADMIN_ROLES = frozenset({"admin", "administrator", "manager", "developer"})


def is_admin(user: Optional[User]) -> bool:
    return bool(user) and (user.role or "").lower() in ADMIN_ROLES


def _require_admin(user: User) -> User:
    if not is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to require admin role.

    Raises HTTPException 403 if user is not an admin.
    Accepts: admin, administrator, manager, developer roles.
    """
    return _require_admin(current_user)


def get_current_admin_detached(
    current_user: User = Depends(get_current_user_detached)
) -> User:
    """get_current_admin for handlers that do slow non-DB work (see get_current_user_detached)."""
    return _require_admin(current_user)


def require_verified_email(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to require verified email.

    Raises HTTPException 403 if email is not verified.
    """
    if not current_user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )
    return current_user


async def require_quarterly_pro(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to require quarterly_pro subscription.

    Checks subscription status via capra-backend and raises HTTPException 403
    if user doesn't have an active quarterly_pro subscription.
    """
    from services.subscription_service import verify_subscription

    result = await verify_subscription(current_user.id)

    if not result.get("hasAccess"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_required",
                "message": "Quarterly Pro subscription required to access the Jobs Portal",
                "planType": result.get("planType", "free"),
                "status": result.get("status", "none"),
                "upgradeUrl": "https://capra.cariara.com"
            }
        )
    return current_user
