"""
Centralized Configuration for JobTrails Backend.

Uses pydantic-settings for environment variable loading and validation.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env" if os.path.exists(".env") else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================================================
    # DATABASE
    # ==========================================================================
    # Read DATABASE_URL from environment first (Railway sets this)
    database_url: str = os.environ.get("DATABASE_URL", "postgresql://chundu@localhost:5432/jobtrails")

    # Connection pool settings (sized for 4 concurrent Celery workers + API)
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 5
    db_pool_recycle: int = 30  # Recycle connections every 30s (Railway may drop idle connections)

    # ==========================================================================
    # REDIS
    # ==========================================================================
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # Cache TTLs (seconds)
    cache_ttl_default: int = 300
    cache_ttl_analytics: int = 300
    cache_ttl_companies: int = 600

    # ==========================================================================
    # CELERY
    # ==========================================================================
    celery_broker_url: Optional[str] = None
    celery_result_backend: Optional[str] = None

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def set_celery_broker(cls, v, info):
        return v or info.data.get("redis_url", "redis://localhost:6379/0")

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def set_celery_backend(cls, v, info):
        return v or info.data.get("redis_url", "redis://localhost:6379/1")

    # ==========================================================================
    # AUTHENTICATION (Phase 2)
    # ==========================================================================
    secret_key: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"

    @property
    def jwt_secret_key(self) -> str:
        """Alias for secret_key for backward compatibility."""
        return self.secret_key
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # ==========================================================================
    # OAUTH PROVIDERS
    # ==========================================================================
    # Google OAuth
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # LinkedIn OAuth
    linkedin_client_id: str = os.environ.get("LINKEDIN_CLIENT_ID", "")
    linkedin_client_secret: str = os.environ.get("LINKEDIN_CLIENT_SECRET", "")

    # GitHub OAuth
    github_client_id: str = os.environ.get("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.environ.get("GITHUB_CLIENT_SECRET", "")

    # OAuth redirect base (frontend URL)
    oauth_redirect_base: str = os.environ.get("OAUTH_REDIRECT_BASE", "http://localhost:3000")

    # Backend URL (for OAuth callbacks)
    backend_url: str = os.environ.get("BACKEND_URL", "http://localhost:8000")

    # ==========================================================================
    # SCRAPER SETTINGS
    # ==========================================================================
    scraper_default_rate_limit: int = 30
    scraper_default_timeout: int = 30
    scraper_max_retries: int = 3
    scraper_schedule_hours: int = 6

    # Browser pool settings
    browser_pool_size: int = 2
    browser_max_pages_per_context: int = 3
    browser_headless: bool = True

    # ==========================================================================
    # API SETTINGS
    # ==========================================================================
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS
    cors_origins: str = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # ==========================================================================
    # EXTERNAL SERVICES
    # ==========================================================================
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    sentry_dsn: str = os.environ.get("SENTRY_DSN", "")

    # Apify API (for cloud-based job scraping)
    apify_api_token: str = os.environ.get("APIFY_API_TOKEN", "")
    apify_webhook_secret: str = os.environ.get("APIFY_WEBHOOK_SECRET", "apify-cariara-2024")

    # ==========================================================================
    # ENVIRONMENT
    # ==========================================================================
    env: str = os.environ.get("ENV", "development")
    debug: bool = os.environ.get("DEBUG", "true").lower() == "true"

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance for backward compatibility
settings = get_settings()
