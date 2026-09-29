"""
Authentication middleware and dependencies.

Provides FastAPI dependencies for protecting routes and getting current user.
Includes token blacklist checking for secure logout/revocation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
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


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user.

    Requires valid Bearer token in Authorization header.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    user = get_current_user(credentials, db)
    db.expunge(user)
    db.rollback()
    return user


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Dependency to optionally get the current user.

    Returns None if not authenticated (instead of raising exception).
    Useful for routes that work both authenticated and unauthenticated.
    """
    if not credentials:
        return None

    try:
        return get_current_user(credentials, db)
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
