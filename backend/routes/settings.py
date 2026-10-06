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

from services.providers import PROVIDERS, PROVIDER_IDS, default_model, models_for, provider_of_model  # noqa: E402

# Database keys for API key storage
API_KEY_DB_KEYS = {pid: p["key_setting"] for pid, p in PROVIDERS.items()}


class APIKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=20, max_length=200)
    provider: Optional[str] = Field(default="openai", description="API provider: " + ", ".join(PROVIDER_IDS))


class APIKeyResponse(BaseModel):
    is_set: bool
    key_preview: Optional[str] = None
    source: Optional[str] = None
    provider: Optional[str] = None


def _provider_or_400(provider: Optional[str]) -> str:
    provider = (provider or "openai").strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider. Valid providers: {list(PROVIDER_IDS)}")
    return provider


def _env_var_set(provider: str) -> Optional[str]:
    """The environment variable holding the provider's key, if one is set."""
    return next((v for v in PROVIDERS[provider]["env"] if os.environ.get(v)), None)


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
    env_var = _env_var_set(provider) if provider in PROVIDERS else None
    if env_var:
        return os.environ[env_var]

    # Fall back to database
    if db:
        return get_api_key_from_db(db, provider)
    return None


def _key_status(provider: str, db: Session) -> APIKeyResponse:
    if get_current_api_key(provider, db):
        # Security: Only show masked placeholder, never reveal actual key characters
        preview = f"{PROVIDERS[provider]['key_prefix']}****...****"
        source = "environment" if _env_var_set(provider) else "database"
        return APIKeyResponse(is_set=True, key_preview=preview, source=source, provider=provider)
    return APIKeyResponse(is_set=False, source=None, provider=provider)


@router.get("/api-key", response_model=APIKeyResponse)
def get_api_key_status(
    provider: str = Query(default="openai", description="API provider id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Check if API key is configured for the specified provider. Requires authentication.
    Returns whether a key is set (without exposing any part of the key).
    """
    return _key_status(_provider_or_400(provider), db)


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
    provider = _provider_or_400(request.provider)
    name = PROVIDERS[provider]["name"]

    if not api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    # Validate format based on provider
    prefix = PROVIDERS[provider]["key_prefix"]
    if not api_key.startswith(prefix):
        raise HTTPException(status_code=400, detail=f"Invalid API key format. {name} keys start with '{prefix}'")

    # Save to database
    db_key = API_KEY_DB_KEYS[provider]
    setting = db.query(AppSetting).filter(AppSetting.key == db_key).first()

    if setting:
        setting.value = api_key
    else:
        setting = AppSetting(
            key=db_key,
            value=api_key,
            description=f"{name} API key for AI features"
        )
        db.add(setting)

    db.commit()
    logger.info(f"{name} API key saved to database")

    return {
        "message": f"{name} API key saved successfully",
        "provider": provider,
        "source": "database"
    }


@router.delete("/api-key")
def remove_api_key(
    provider: str = Query(default="openai", description="API provider id"),
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

    provider = _provider_or_400(provider)
    name = PROVIDERS[provider]["name"]
    env_var = _env_var_set(provider)

    # If key was set via environment, we can't remove it
    if env_var:
        return {
            "message": f"Cannot remove {name} API key",
            "warning": f"Key is set via environment variable {env_var}. Remove it from server configuration."
        }

    # Remove from database
    setting = db.query(AppSetting).filter(AppSetting.key == API_KEY_DB_KEYS[provider]).first()
    if setting:
        db.delete(setting)
        db.commit()
        logger.info(f"{name} API key removed from database")

    return {"message": f"{name} API key removed successfully"}


# Cheapest current model; count_tokens against it validates the key.
TEST_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# ============== Default AI Provider Settings ==============

class DefaultProviderRequest(BaseModel):
    provider: str = Field(..., description="AI provider id: " + ", ".join(PROVIDER_IDS))


def get_default_ai_provider(db: Session) -> str:
    """Get the configured default AI provider from database."""
    setting = db.query(AppSetting).filter(AppSetting.key == "default_ai_provider").first()
    if setting and setting.value in PROVIDER_IDS:
        return setting.value
    from services.ai_service import DEFAULT_PROVIDER
    return DEFAULT_PROVIDER


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
    provider = _provider_or_400(request.provider)
    setting = db.query(AppSetting).filter(AppSetting.key == "default_ai_provider").first()

    if setting:
        setting.value = provider
    else:
        setting = AppSetting(
            key="default_ai_provider",
            value=provider,
            description="Default AI provider for AI-powered features"
        )
        db.add(setting)

    db.commit()
    logger.info(f"Default AI provider set to {provider}")

    return {"provider": provider, "message": f"Default provider set to {provider}"}


# ============== AI Model Settings ==============

from services.anthropic_service import resolve_claude_model  # noqa: E402


def _model_options(models: dict) -> list[dict]:
    """{id: "Name (Blurb)"} -> [{id, name, description}] for the admin UI."""
    options = []
    for model_id, label in models.items():
        name, _, rest = label.partition(" (")
        options.append({"id": model_id, "name": name, "description": rest.rstrip(")")})
    return options


def _saved_model(db: Session, provider: str) -> str:
    """The provider's chosen model, or its default when unset or no longer offered."""
    setting = db.query(AppSetting).filter(AppSetting.key == PROVIDERS[provider]["model_setting"]).first()
    value = setting.value if setting and setting.value else None
    if provider == "anthropic" and value:
        # A stale saved id (e.g. a retired Claude 3 model) maps to its successor.
        return resolve_claude_model(value)
    return value if value in models_for(provider) else default_model(provider)


class AIModelRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=100, description="AI model to use")


@router.get("/ai-model")
def get_ai_model_setting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Every provider with its models, chosen model and key status, plus the default provider."""
    providers = [
        {
            "id": pid,
            "name": PROVIDERS[pid]["name"],
            "model": _saved_model(db, pid),
            "models": _model_options(models_for(pid)),
            "key": _key_status(pid, db).model_dump(),
        }
        for pid in PROVIDER_IDS
    ]
    by_id = {p["id"]: p for p in providers}
    return {
        "default_provider": get_default_ai_provider(db),
        "providers": providers,
        # The fields older admin pages read.
        "openai_model": by_id["openai"]["model"],
        "claude_model": by_id["anthropic"]["model"],
        "openai_models": by_id["openai"]["models"],
        "claude_models": by_id["anthropic"]["models"],
    }


@router.post("/ai-model")
def set_ai_model(
    request: AIModelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Set a provider's model; the model id says which provider it belongs to."""
    model = request.model.strip()
    if model.startswith("claude-3"):
        # Legacy Claude 3 ids are accepted but stored as their current successor.
        model = resolve_claude_model(model)
    provider = provider_of_model(model)
    if not provider:
        valid = {pid: list(models_for(pid)) for pid in PROVIDER_IDS}
        raise HTTPException(status_code=400, detail=f"Invalid model. Valid models: {valid}")

    db_key = PROVIDERS[provider]["model_setting"]
    name = PROVIDERS[provider]["name"]
    setting = db.query(AppSetting).filter(AppSetting.key == db_key).first()

    if setting:
        setting.value = model
    else:
        setting = AppSetting(
            key=db_key,
            value=model,
            description=f"{name} model for AI-powered features"
        )
        db.add(setting)

    db.commit()
    logger.info(f"{name} model set to {model}")

    return {"model": model, "provider": "Claude" if provider == "anthropic" else name, "provider_id": provider,
            "message": f"{'Claude' if provider == 'anthropic' else name} model set to {model}"}


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
