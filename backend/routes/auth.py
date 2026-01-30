"""
Authentication routes.

Handles user registration, login, token refresh, and logout.
Includes Redis-backed token blacklist for secure logout/revocation.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

try:
    from database import get_db
    from models import User
    from schemas.auth import (
        UserRegister, UserLogin, TokenResponse, TokenRefresh,
        UserResponse, UserUpdate, PasswordChange
    )
    from utils.security import (
        hash_password, verify_password,
        create_access_token, create_refresh_token, decode_token
    )
    from middleware.auth import get_current_user
    from config import settings
    from services.redis_service import redis_service
except ImportError:
    from database import get_db
    from models import User
    from schemas.auth import (
        UserRegister, UserLogin, TokenResponse, TokenRefresh,
        UserResponse, UserUpdate, PasswordChange
    )
    from utils.security import (
        hash_password, verify_password,
        create_access_token, create_refresh_token, decode_token
    )
    from middleware.auth import get_current_user
    from config import settings
    from services.redis_service import redis_service


router = APIRouter(prefix="/auth", tags=["Authentication"])

# Account lockout settings
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user account.

    Returns access and refresh tokens on success.
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    user = User(
        email=user_data.email.lower(),
        name=user_data.name,
        password_hash=hash_password(user_data.password),
        is_email_verified=False,
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate tokens
    access_token, _ = create_access_token(user.id, user.email, user.role)
    refresh_token, _ = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_email_verified=user.is_email_verified,
            onboarding_completed=user.onboarding_completed or False,
            job_roles=user.job_roles or [],
            roles_confirmed_at=user.roles_confirmed_at,
            created_at=user.created_at,
        )
    )


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate user and return tokens.
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email.lower()).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = (user.locked_until - datetime.now(timezone.utc)).seconds // 60
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Account is locked. Try again in {remaining} minutes."
        )

    # Check if user has a password (might be migrated user without password)
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please reset your password to activate your account"
        )

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        # Increment failed attempts
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        # Lock account if too many failures
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Too many failed attempts. Account locked for {LOCKOUT_DURATION_MINUTES} minutes."
            )

        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled"
        )

    # Reset failed attempts and update last login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # Generate tokens
    access_token, _ = create_access_token(user.id, user.email, user.role)
    refresh_token, _ = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_email_verified=user.is_email_verified or False,
            onboarding_completed=user.onboarding_completed or False,
            created_at=user.created_at,
        )
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token.
    """
    payload = decode_token(token_data.refresh_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    # Get user
    user_id = int(payload.get("sub"))
    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled"
        )

    # Blacklist the old refresh token
    old_jti = payload.get("jti")
    if old_jti:
        # TTL should be remaining time on the old token
        exp = payload.get("exp", 0)
        remaining_ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
        redis_service.blacklist_token(old_jti, remaining_ttl)

    # Generate new tokens
    access_token, _ = create_access_token(user.id, user.email, user.role)
    new_refresh_token, _ = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_email_verified=user.is_email_verified or False,
            onboarding_completed=user.onboarding_completed or False,
            created_at=user.created_at,
        )
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current user's profile.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        is_email_verified=current_user.is_email_verified or False,
        onboarding_completed=current_user.onboarding_completed or False,
        job_roles=current_user.job_roles or [],
        roles_confirmed_at=current_user.roles_confirmed_at,
        created_at=current_user.created_at,
    )


@router.put("/me", response_model=UserResponse)
def update_me(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile.
    """
    if user_data.name is not None:
        current_user.name = user_data.name
    if user_data.target_seniority is not None:
        current_user.target_seniority = user_data.target_seniority
    if user_data.min_salary is not None:
        current_user.min_salary = user_data.min_salary
    if user_data.preferred_locations is not None:
        current_user.preferred_locations = user_data.preferred_locations

    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_user)

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        is_email_verified=current_user.is_email_verified or False,
        onboarding_completed=current_user.onboarding_completed or False,
        job_roles=current_user.job_roles or [],
        roles_confirmed_at=current_user.roles_confirmed_at,
        created_at=current_user.created_at,
    )


@router.post("/change-password")
def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change current user's password.
    """
    # Verify current password
    if not current_user.password_hash or not verify_password(
        password_data.current_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Update password
    current_user.password_hash = hash_password(password_data.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    authorization: Optional[str] = Header(None),
    refresh_token: Optional[str] = None,
):
    """
    Logout user and invalidate tokens.

    Optionally accepts refresh_token in body to blacklist it.
    The access token from Authorization header is also blacklisted.
    """
    tokens_blacklisted = 0

    # Blacklist the access token from header
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization[7:]
        payload = decode_token(access_token)
        if payload:
            jti = payload.get("jti")
            if jti:
                exp = payload.get("exp", 0)
                remaining_ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
                if redis_service.blacklist_token(jti, remaining_ttl):
                    tokens_blacklisted += 1

    # Blacklist the refresh token if provided
    if refresh_token:
        payload = decode_token(refresh_token)
        if payload and payload.get("type") == "refresh":
            jti = payload.get("jti")
            if jti:
                exp = payload.get("exp", 0)
                remaining_ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
                if redis_service.blacklist_token(jti, remaining_ttl):
                    tokens_blacklisted += 1

    return {
        "message": "Logged out successfully",
        "tokens_invalidated": tokens_blacklisted
    }


@router.post("/logout-all")
def logout_all_sessions(current_user: User = Depends(get_current_user)):
    """
    Logout from all sessions/devices.

    Invalidates all tokens issued before this moment.
    """
    # Blacklist all tokens for this user
    # TTL should be the max token lifetime (refresh token expiry)
    max_token_ttl = settings.jwt_refresh_token_expire_days * 24 * 60 * 60
    redis_service.blacklist_user_tokens(current_user.id, max_token_ttl)

    return {
        "message": "Logged out from all sessions successfully",
        "user_id": current_user.id
    }
