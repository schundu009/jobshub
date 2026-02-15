"""
Settings routes for managing application configuration.

Security notes:
- JWT authentication required for all endpoints
- API keys are stored in environment variables only (not persisted to files in production)
- In production, set OPENAI_API_KEY via environment variable before starting the app
- The set_api_key endpoint is for development/testing convenience only
- Production deployments should disable API key modification via ALLOW_API_KEY_MODIFICATION=false
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Literal
import os
import logging

from database import get_db
from models import User, AppSetting
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)

# Security configuration
# In production, set ALLOW_API_KEY_MODIFICATION=false to prevent API key changes via API
ALLOW_API_KEY_MODIFICATION = os.getenv("ALLOW_API_KEY_MODIFICATION", "true").lower() == "true"

# Store API key in memory for session (NOT persisted to files in production)
_api_key_cache = os.environ.get('OPENAI_API_KEY')


class APIKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=20, max_length=200)


class APIKeyResponse(BaseModel):
    is_set: bool
    key_preview: Optional[str] = None
    source: Optional[str] = None


def get_current_api_key() -> Optional[str]:
    """Get current API key from environment or cache."""
    return os.environ.get('OPENAI_API_KEY') or _api_key_cache


@router.get("/api-key", response_model=APIKeyResponse)
def get_api_key_status(current_user: User = Depends(get_current_user)):
    """
    Check if OpenAI API key is configured. Requires authentication.
    Returns whether a key is set (without exposing any part of the key).
    """
    api_key = get_current_api_key()

    if api_key:
        # Security: Only show masked placeholder, never reveal actual key characters
        preview = "sk-****...****"

        # Indicate source of the key
        source = "environment" if os.environ.get('OPENAI_API_KEY') else "session"

        return APIKeyResponse(is_set=True, key_preview=preview, source=source)

    return APIKeyResponse(is_set=False, source=None)


@router.post("/api-key")
def set_api_key(request: APIKeyRequest, current_user: User = Depends(get_current_user)):
    """
    Set the OpenAI API key for this session. Requires authentication.

    Security notes:
    - Key is stored in memory only (not persisted to disk)
    - In production, disable this endpoint by setting ALLOW_API_KEY_MODIFICATION=false
    - For production, set OPENAI_API_KEY environment variable before starting the app
    """
    global _api_key_cache

    # Check if modification is allowed
    if not ALLOW_API_KEY_MODIFICATION:
        raise HTTPException(
            status_code=403,
            detail="API key modification is disabled in production. Set OPENAI_API_KEY environment variable."
        )

    api_key = request.api_key.strip()

    if not api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    # Validate format (OpenAI keys start with sk-)
    if not api_key.startswith("sk-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid API key format. OpenAI keys start with 'sk-'"
        )

    # Store in environment variable for this session
    os.environ['OPENAI_API_KEY'] = api_key
    _api_key_cache = api_key

    logger.info("OpenAI API key set via API (session only, not persisted)")

    return {
        "message": "API key saved for this session",
        "warning": "Key is stored in memory only. Set OPENAI_API_KEY environment variable for persistence."
    }


@router.delete("/api-key")
def remove_api_key(current_user: User = Depends(get_current_user)):
    """
    Remove the stored OpenAI API key from this session. Requires authentication.

    Note: This only removes the session key. Environment variable keys cannot be removed via API.
    """
    global _api_key_cache

    if not ALLOW_API_KEY_MODIFICATION:
        raise HTTPException(
            status_code=403,
            detail="API key modification is disabled in production."
        )

    # Only remove session cache, not environment variable
    _api_key_cache = None

    # If key was set via environment, we can't really remove it
    if os.environ.get('OPENAI_API_KEY'):
        return {
            "message": "Session API key cleared",
            "warning": "Environment variable OPENAI_API_KEY is still set. Restart the app to clear it."
        }

    return {"message": "API key removed successfully"}


@router.get("/test-api-key")
def test_api_key(current_user: User = Depends(get_current_user)):
    """
    Test if the configured OpenAI API key is valid. Requires authentication.
    Makes a minimal API call to validate the key.
    """
    api_key = get_current_api_key()

    if not api_key:
        raise HTTPException(status_code=400, detail="No API key configured")

    return _test_openai_key(api_key)


@router.post("/test-api-key")
def test_api_key_with_key(request: APIKeyRequest, current_user: User = Depends(get_current_user)):
    """
    Test a provided OpenAI API key without saving it. Requires authentication.
    Useful for validating a key before saving.
    """
    return _test_openai_key(request.api_key.strip())


def _test_openai_key(api_key: str) -> dict:
    """Internal function to test an OpenAI API key."""
    if not api_key:
        return {"valid": False, "message": "No API key provided"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # Make a minimal API call to test the key
        client.models.list()
        return {"valid": True, "message": "API key is valid"}
    except Exception as e:
        error_msg = str(e)
        if "invalid_api_key" in error_msg.lower() or "401" in error_msg:
            return {"valid": False, "message": "Invalid API key"}
        if "rate_limit" in error_msg.lower() or "429" in error_msg:
            return {"valid": True, "message": "API key is valid (rate limited)"}
        return {"valid": False, "message": f"Error testing key: {error_msg[:100]}"}


@router.get("/security")
def get_security_settings(current_user: User = Depends(get_current_user)):
    """
    Get current security configuration status. Requires authentication.
    """
    return {
        "api_key_modification_allowed": ALLOW_API_KEY_MODIFICATION,
        "api_key_source": "environment" if os.environ.get('OPENAI_API_KEY') else ("session" if _api_key_cache else "none"),
        "ssl_verification": os.getenv("DISABLE_SSL_VERIFY", "false").lower() != "true",
        "debug_mode": os.getenv("DEBUG", "false").lower() == "true",
    }


# ============== Job Age Filter Settings ==============

# Default max job age in days
DEFAULT_MAX_JOB_AGE_DAYS = 30

# Valid options for max job age
VALID_JOB_AGE_OPTIONS = [7, 14, 30]


class MaxJobAgeRequest(BaseModel):
    days: Literal[7, 14, 30] = Field(..., description="Maximum job age in days (7, 14, or 30)")


def get_max_job_age_days(db: Session) -> int:
    """
    Get the configured max job age setting from database.
    Falls back to DEFAULT_MAX_JOB_AGE_DAYS if not set.
    """
    setting = db.query(AppSetting).filter(AppSetting.key == "max_job_age_days").first()
    if setting:
        try:
            return int(setting.value)
        except ValueError:
            return DEFAULT_MAX_JOB_AGE_DAYS
    return DEFAULT_MAX_JOB_AGE_DAYS


@router.get("/job-age-filter")
def get_job_age_filter(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the current max job age filter setting.
    Jobs older than this will be skipped during scraping.
    """
    current_days = get_max_job_age_days(db)
    return {
        "max_job_age_days": current_days,
        "valid_options": VALID_JOB_AGE_OPTIONS,
        "description": f"Only fetch jobs posted within the last {current_days} days"
    }


@router.post("/job-age-filter")
def set_job_age_filter(
    request: MaxJobAgeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set the max job age filter. Admin only.
    Jobs older than this will be skipped during scraping to save resources.
    """
    # Admin check
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Validate the value
    if request.days not in VALID_JOB_AGE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value. Must be one of: {VALID_JOB_AGE_OPTIONS}"
        )

    # Get or create the setting
    setting = db.query(AppSetting).filter(AppSetting.key == "max_job_age_days").first()

    if setting:
        setting.value = str(request.days)
    else:
        setting = AppSetting(
            key="max_job_age_days",
            value=str(request.days),
            description="Maximum age (in days) for jobs to fetch from ATS sources"
        )
        db.add(setting)

    db.commit()

    logger.info(f"Max job age filter set to {request.days} days by user {current_user.email}")

    return {
        "message": f"Job age filter updated to {request.days} days",
        "max_job_age_days": request.days
    }
