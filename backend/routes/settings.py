"""
Settings routes for managing application configuration.

Security notes:
- Admin role required for all endpoints (router-level dependency)
- API keys are stored in the database (encrypted in transit via HTTPS)
- Environment variables take precedence over database values
- Production deployments can disable API key modification via ALLOW_API_KEY_MODIFICATION=false
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Literal
import os
import logging

from database import get_db
from models import User, AppSetting
from middleware.auth import get_current_admin

# Every settings endpoint is admin-only: they reveal/modify provider keys,
# the default AI provider/model and global scrape filters.
router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(get_current_admin)],
)
logger = logging.getLogger(__name__)

# Security configuration
# In production, set ALLOW_API_KEY_MODIFICATION=false to prevent API key changes via API
ALLOW_API_KEY_MODIFICATION = os.getenv("ALLOW_API_KEY_MODIFICATION", "true").lower() == "true"

# Database keys for API key storage
API_KEY_DB_KEYS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key"
}


class APIKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=20, max_length=200)
    provider: Optional[str] = Field(default="openai", description="API provider: 'openai' or 'anthropic'")


class APIKeyResponse(BaseModel):
    is_set: bool
    key_preview: Optional[str] = None
    source: Optional[str] = None
    provider: Optional[str] = None


def get_api_key_from_db(db: Session, provider: str) -> Optional[str]:
    """Get API key from database for the specified provider."""
    db_key = API_KEY_DB_KEYS.get(provider)
    if not db_key:
        return None
    setting = db.query(AppSetting).filter(AppSetting.key == db_key).first()
    return setting.value if setting else None


def get_current_api_key(provider: str = "openai", db: Session = None) -> Optional[str]:
    """Get current API key from environment or database for the specified provider."""
    # Environment variables take precedence
    env_var = 'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY'
    env_key = os.environ.get(env_var)
    if env_key:
        return env_key

    # Fall back to database
    if db:
        return get_api_key_from_db(db, provider)
    return None


@router.get("/api-key", response_model=APIKeyResponse)
def get_api_key_status(
    provider: str = Query(default="openai", description="API provider: 'openai' or 'anthropic'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Check if API key is configured for the specified provider. Requires authentication.
    Returns whether a key is set (without exposing any part of the key).
    """
    env_var = 'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY'
    api_key = get_current_api_key(provider, db)

    if api_key:
        # Security: Only show masked placeholder, never reveal actual key characters
        preview = "sk-ant-****...****" if provider == 'anthropic' else "sk-****...****"

        # Indicate source of the key
        if os.environ.get(env_var):
            source = "environment"
        else:
            source = "database"

        return APIKeyResponse(is_set=True, key_preview=preview, source=source, provider=provider)

    return APIKeyResponse(is_set=False, source=None, provider=provider)


@router.post("/api-key")
def set_api_key(
    request: APIKeyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Set the API key for the specified provider. Requires authentication.
    Key is persisted to the database for cross-session availability.
    """
    # Check if modification is allowed
    if not ALLOW_API_KEY_MODIFICATION:
        raise HTTPException(
            status_code=403,
            detail="API key modification is disabled in production. Set environment variable."
        )

    api_key = request.api_key.strip()
    provider = request.provider or "openai"

    if not api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    # Validate format based on provider
    if provider == "anthropic":
        if not api_key.startswith("sk-ant-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid API key format. Anthropic keys start with 'sk-ant-'"
            )
    else:
        if not api_key.startswith("sk-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid API key format. OpenAI keys start with 'sk-'"
            )

    # Save to database
    db_key = API_KEY_DB_KEYS.get(provider)
    setting = db.query(AppSetting).filter(AppSetting.key == db_key).first()

    if setting:
        setting.value = api_key
    else:
        setting = AppSetting(
            key=db_key,
            value=api_key,
            description=f"{provider.title()} API key for AI features"
        )
        db.add(setting)

    db.commit()
    logger.info(f"{provider.title()} API key saved to database")

    return {
        "message": f"{provider.title()} API key saved successfully",
        "provider": provider,
        "source": "database"
    }


@router.delete("/api-key")
def remove_api_key(
    provider: str = Query(default="openai", description="API provider: 'openai' or 'anthropic'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Remove the stored API key for the specified provider. Requires authentication.
    Removes from database. Environment variable keys cannot be removed via API.
    """
    if not ALLOW_API_KEY_MODIFICATION:
        raise HTTPException(
            status_code=403,
            detail="API key modification is disabled in production."
        )

    env_var = 'ANTHROPIC_API_KEY' if provider == 'anthropic' else 'OPENAI_API_KEY'

    # If key was set via environment, we can't remove it
    if os.environ.get(env_var):
        return {
            "message": f"Cannot remove {provider} API key",
            "warning": f"Key is set via environment variable {env_var}. Remove it from server configuration."
        }

    # Remove from database
    db_key = API_KEY_DB_KEYS.get(provider)
    setting = db.query(AppSetting).filter(AppSetting.key == db_key).first()
    if setting:
        db.delete(setting)
        db.commit()
        logger.info(f"{provider.title()} API key removed from database")

    return {"message": f"{provider.title()} API key removed successfully"}


# Cheapest current model; count_tokens against it validates the key.
TEST_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# ============== Default AI Provider Settings ==============

class DefaultProviderRequest(BaseModel):
    provider: Literal["openai", "anthropic"] = Field(..., description="AI provider: 'openai' or 'anthropic'")


def get_default_ai_provider(db: Session) -> str:
    """Get the configured default AI provider from database."""
    setting = db.query(AppSetting).filter(AppSetting.key == "default_ai_provider").first()
    if setting and setting.value in ["openai", "anthropic"]:
        return setting.value
    return "openai"  # Default to OpenAI


@router.get("/default-ai-provider")
def get_default_provider(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get the default AI provider for AI features."""
    provider = get_default_ai_provider(db)
    return {"provider": provider}


@router.post("/default-ai-provider")
def set_default_provider(
    request: DefaultProviderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Set the default AI provider for AI features."""
    setting = db.query(AppSetting).filter(AppSetting.key == "default_ai_provider").first()

    if setting:
        setting.value = request.provider
    else:
        setting = AppSetting(
            key="default_ai_provider",
            value=request.provider,
            description="Default AI provider for AI-powered features"
        )
        db.add(setting)

    db.commit()
    logger.info(f"Default AI provider set to {request.provider}")

    return {"provider": request.provider, "message": f"Default provider set to {request.provider}"}


# ============== AI Model Settings ==============

from services.anthropic_service import (  # noqa: E402  single source of truth
    CLAUDE_MODELS,
    DEFAULT_MODEL as DEFAULT_CLAUDE_MODEL,
    resolve_claude_model,
)
from services.openai_service import (  # noqa: E402
    OPENAI_MODELS,
    DEFAULT_MODEL as DEFAULT_OPENAI_MODEL,
)

VALID_OPENAI_MODELS = list(OPENAI_MODELS)
VALID_CLAUDE_MODELS = list(CLAUDE_MODELS)


def _model_options(models: dict) -> list[dict]:
    """{id: "Name (Blurb)"} -> [{id, name, description}] for the admin UI."""
    options = []
    for model_id, label in models.items():
        name, _, rest = label.partition(" (")
        options.append({"id": model_id, "name": name, "description": rest.rstrip(")")})
    return options


class AIModelRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=100, description="AI model to use")


@router.get("/ai-model")
def get_ai_model_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get the configured AI models for both providers."""
    openai_setting = db.query(AppSetting).filter(AppSetting.key == "ai_model").first()
    claude_setting = db.query(AppSetting).filter(AppSetting.key == "claude_model").first()

    openai_model = openai_setting.value if openai_setting and openai_setting.value in VALID_OPENAI_MODELS else DEFAULT_OPENAI_MODEL
    # A stale saved id (e.g. a retired Claude 3 model) maps to its successor.
    claude_model = resolve_claude_model(claude_setting.value) if claude_setting and claude_setting.value else DEFAULT_CLAUDE_MODEL

    return {
        "openai_model": openai_model,
        "claude_model": claude_model,
        "openai_models": _model_options(OPENAI_MODELS),
        "claude_models": _model_options(CLAUDE_MODELS),
    }


@router.post("/ai-model")
def set_ai_model(
    request: AIModelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Set the AI model to use for AI features."""
    model = request.model.strip()

    # Determine if it's OpenAI or Claude model
    if model in VALID_OPENAI_MODELS:
        db_key = "ai_model"
        provider = "OpenAI"
    elif model in VALID_CLAUDE_MODELS or model.startswith("claude-3"):
        # Legacy Claude 3 ids are accepted but stored as their current successor.
        model = resolve_claude_model(model)
        db_key = "claude_model"
        provider = "Claude"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Valid OpenAI models: {VALID_OPENAI_MODELS}. Valid Claude models: {VALID_CLAUDE_MODELS}"
        )

    setting = db.query(AppSetting).filter(AppSetting.key == db_key).first()

    if setting:
        setting.value = model
    else:
        setting = AppSetting(
            key=db_key,
            value=model,
            description=f"{provider} model for AI-powered features"
        )
        db.add(setting)

    db.commit()
    logger.info(f"{provider} model set to {model}")

    return {"model": model, "provider": provider, "message": f"{provider} model set to {model}"}


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
    current_user: User = Depends(get_current_admin)
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
    current_user: User = Depends(get_current_admin)
):
    """
    Set the max job age filter. Admin only.
    Jobs older than this will be skipped during scraping to save resources.
    """
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
