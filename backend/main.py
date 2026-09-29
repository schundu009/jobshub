"""
Cariara API - Main Application Entry Point
Version: 2.1.0 - With onboarding support

Security features:
- CORS restricted to configured origins
- Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- API key authentication for sensitive endpoints
- Rate limiting
- No-cache headers for API responses
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from contextlib import asynccontextmanager
import anyio
import anyio.to_thread
import os
import time
import logging
import traceback
from collections import defaultdict
from typing import Optional
from sqlalchemy.orm import Session

from database import create_tables
from routes import jobs, companies, contacts, interviews, notes, documents, ai, analytics, ingest, settings, users, scrapers, auth, oauth, internal_auth, celery_management, apify, auto_heal
# auto_apply routes disabled - users now apply manually with downloaded CV/CL
from config import settings as app_settings
from services.redis_service import redis_service

# Observability
from observability import setup_logging, get_logger, metrics, MetricsMiddleware, ObservabilityMiddleware

# Set up structured logging based on environment
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("ENV", "development").lower() in ("production", "staging")
)

logger = get_logger(__name__)


# =============================================================================
# Security Configuration
# =============================================================================

# Allowed origins for CORS - configure via environment variable
# Format: comma-separated list of origins, e.g., "http://localhost:8000,https://myapp.com"
_REQUIRED_ORIGINS = [
    "https://jobs.cariara.com",
    "https://admin.cariara.com",
    "https://cariara.com",
    "https://www.cariara.com",
]
_DEFAULT_ORIGINS = (
    "http://localhost:3000,http://localhost:8000,http://localhost:8001,"
    "http://127.0.0.1:3000,http://127.0.0.1:8000,http://127.0.0.1:8001,"
    "https://cariara.com,https://www.cariara.com,https://jobs.cariara.com,"
    "https://admin.cariara.com,https://jobportal-ten-blush.vercel.app,"
    "https://jobportal-schundu007.vercel.app,https://jobportal-ihvmibgpi-schundu007.vercel.app"
)
_env_origins = os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
# Always include required production origins regardless of ALLOWED_ORIGINS env var
ALLOWED_ORIGINS = list(dict.fromkeys(_env_origins + _REQUIRED_ORIGINS))

# API Key for authentication (optional - if set, requires X-API-Key header)
API_KEY = os.getenv("JOBTRAILS_API_KEY", "")

# Rate limiting configuration
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))  # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # window in seconds

# Public endpoints that don't require authentication
# All /api/* endpoints are now protected by JWT auth via middleware/auth.py
PUBLIC_ENDPOINTS = {
    # App root & docs
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    # Health checks
    "/health",
    "/health/redis",
    # Auth endpoints (login/register flow)
    "/auth/providers",
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    # OAuth flows
    "/auth/google/login",
    "/auth/google/callback",
    "/auth/github/login",
    "/auth/github/callback",
    "/auth/linkedin/login",
    "/auth/linkedin/callback",
}


# =============================================================================
# Rate Limiting Configuration
# =============================================================================

# Rate limits per endpoint category
RATE_LIMITS = {
    "auth": {"limit": 20, "window": 60},       # 20 requests/minute for auth
    "auth_login": {"limit": 10, "window": 60}, # 10 login attempts/minute
    "api_read": {"limit": 500, "window": 60},  # 500 reads/minute
    "api_write": {"limit": 300, "window": 60}, # 300 writes/minute
    "scraper": {"limit": 30, "window": 3600},  # 30 scraper triggers/hour
    "default": {"limit": RATE_LIMIT_REQUESTS, "window": RATE_LIMIT_WINDOW},
}


class RateLimiter:
    """
    Distributed rate limiter using Redis.

    Falls back to in-memory limiting if Redis is unavailable.
    """

    def __init__(self, requests_per_window: int = 100, window_seconds: int = 60):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        # Fallback in-memory storage
        self._fallback_requests = defaultdict(list)
        self._use_redis = True

    def _check_redis(self) -> bool:
        """Whether to try Redis for this request.

        No per-request PING: the Redis service keeps a short-lived circuit
        breaker that trips on connection errors/timeouts, so a down Redis
        costs nothing and we fall back to in-memory limiting.
        """
        return self._use_redis and redis_service.available

    def is_allowed(
        self,
        client_id: str,
        endpoint_category: str = "default"
    ) -> tuple[bool, int, int]:
        """
        Check if request is allowed for this client.

        Returns:
            Tuple of (is_allowed, remaining, retry_after)
        """
        # Get rate limit config for this category
        config = RATE_LIMITS.get(endpoint_category, RATE_LIMITS["default"])
        limit = config["limit"]
        window = config["window"]

        # Try Redis first (fails open; trips the circuit on connection errors)
        if self._check_redis():
            result = redis_service.check_rate_limit(
                client_id, limit, window, endpoint_category
            )
            if redis_service.available:
                return result

        # Fallback to in-memory
        return self._in_memory_check((client_id, endpoint_category), limit, window)

    def _in_memory_check(
        self,
        client_id: tuple[str, str],
        limit: int,
        window: int
    ) -> tuple[bool, int, int]:
        """In-memory rate limit check (fallback)."""
        now = time.time()
        window_start = now - window

        # Clean old requests
        self._fallback_requests[client_id] = [
            req_time for req_time in self._fallback_requests[client_id]
            if req_time > window_start
        ]

        # Check if under limit
        if len(self._fallback_requests[client_id]) >= limit:
            retry_after = int(self._fallback_requests[client_id][0] + window - now) + 1
            return False, 0, retry_after

        # Record this request
        self._fallback_requests[client_id].append(now)
        remaining = limit - len(self._fallback_requests[client_id])
        return True, remaining, 0

    def get_remaining(self, client_id: str, endpoint_category: str = "default") -> int:
        """Get remaining requests for this client."""
        config = RATE_LIMITS.get(endpoint_category, RATE_LIMITS["default"])
        limit = config["limit"]
        window = config["window"]

        if self._check_redis():
            status = redis_service.get_rate_limit_status(
                client_id, limit, window, endpoint_category
            )
            return status["remaining"]

        # Fallback
        now = time.time()
        window_start = now - window
        current = len([
            t for t in self._fallback_requests[(client_id, endpoint_category)] if t > window_start
        ])
        return max(0, limit - current)


rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)


# =============================================================================
# Security Middleware
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Cache control for API endpoints
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response


_RATE_LIMIT_EXEMPT_PATHS = {"/health", "/health/db", "/health/redis", "/metrics"}
_RATE_LIMIT_THREADS = anyio.CapacityLimiter(20)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with endpoint-specific limits."""

    def _get_endpoint_category(self, path: str, method: str) -> str:
        """Determine the rate limit category for this endpoint."""
        # Auth endpoints
        if path.startswith("/auth/"):
            if path == "/auth/login":
                return "auth_login"
            return "auth"

        # Scraper endpoints - only limit actual scraper triggers, not management
        if method == "POST":
            # These are the actual scraper/ingestion triggers that should be limited
            # Exclude batch management endpoints (async, stop, status)
            if "/refresh" in path:
                # Don't limit batch/async, stop, status, or logs endpoints
                if "/batch/" in path or "/stop" in path or "/status" in path or "/logs" in path:
                    pass  # Let these go through normal API rate limiting
                elif path.startswith("/api/scrapers") or path.startswith("/api/ingest"):
                    return "scraper"
            # Webhook triggers
            if "/webhook/trigger" in path:
                return "scraper"

        # API endpoints
        if path.startswith("/api/"):
            if method in ("POST", "PUT", "DELETE", "PATCH"):
                return "api_write"
            return "api_read"

        return "default"

    async def dispatch(self, request: Request, call_next):
        # Health checks and CORS preflights must never wait on Redis.
        if request.method == "OPTIONS" or request.url.path in _RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        # Get client identifier
        # Prefer user ID from token, fall back to IP
        client_id = request.client.host if request.client else "unknown"

        # Authentication attempts always share an IP bucket. Only verified access
        # tokens may select a user bucket for other endpoints.
        if not request.url.path.startswith("/auth/"):
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                from utils.security import decode_token
                payload = decode_token(auth_header[7:])
                if payload and payload.get("type") == "access":
                    subject = payload.get("sub")
                    if isinstance(subject, str) and subject.isdecimal():
                        client_id = f"user:{int(subject)}"

        # Get endpoint category
        path = request.url.path
        method = request.method
        category = self._get_endpoint_category(path, method)

        # Check rate limit off the event loop (Redis I/O is blocking). Uses a
        # dedicated limiter so it never queues behind DB-bound handler threads.
        is_allowed, remaining, retry_after = await anyio.to_thread.run_sync(
            rate_limiter.is_allowed, client_id, category, limiter=_RATE_LIMIT_THREADS
        )

        config = RATE_LIMITS.get(category, RATE_LIMITS["default"])

        if not is_allowed:
            return Response(
                content='{"detail": "Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(config["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Category": category,
                }
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(config["limit"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Category"] = category

        return response


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """API Key authentication middleware for sensitive endpoints."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth if no API key is configured
        if not API_KEY:
            return await call_next(request)

        # Skip auth for public endpoints
        path = request.url.path
        if path in PUBLIC_ENDPOINTS:
            return await call_next(request)

        # Skip auth for static files
        if path == "/static" or path.startswith("/static/"):
            return await call_next(request)

        # Skip auth for GET requests to read-only endpoints
        if request.method == "GET" and path.startswith("/api/"):
            return await call_next(request)

        # Check API key for write operations
        api_key = request.headers.get("X-API-Key")
        if api_key != API_KEY:
            return Response(
                content='{"detail": "Invalid or missing API key"}',
                status_code=401,
                media_type="application/json"
            )

        return await call_next(request)


# =============================================================================
# Application Setup
# =============================================================================

def run_migrations():
    """Run database migrations to add new columns."""
    from sqlalchemy import text
    from database import engine

    # New columns to add to users table
    new_user_columns = [
        ("role", "VARCHAR(20) DEFAULT 'user'"),
        ("first_name", "VARCHAR(100)"),
        ("last_name", "VARCHAR(100)"),
        ("preferred_name", "VARCHAR(100)"),
        ("phone", "VARCHAR(50)"),
        ("country", "VARCHAR(50)"),
        ("address_line1", "VARCHAR(255)"),
        ("address_line2", "VARCHAR(255)"),
        ("city", "VARCHAR(100)"),
        ("state", "VARCHAR(100)"),
        ("postal_code", "VARCHAR(20)"),
        ("address_country", "VARCHAR(50)"),
        ("us_authorized", "VARCHAR(20)"),
        ("requires_sponsorship", "VARCHAR(20)"),
        ("willing_to_relocate", "VARCHAR(20)"),
        ("us_government_employee", "VARCHAR(20)"),
        ("non_compete", "VARCHAR(20)"),
        ("work_arrangement", "VARCHAR(20)"),
        ("linkedin_url", "VARCHAR(500)"),
        ("github_url", "VARCHAR(500)"),
        ("portfolio_url", "VARCHAR(500)"),
        ("twitter_url", "VARCHAR(500)"),
        ("referral_source", "VARCHAR(50)"),
        ("bio", "TEXT"),
        ("skills", "TEXT"),
        # Demographics / EEO fields
        ("gender", "VARCHAR(20)"),
        ("ethnicity", "VARCHAR(50)"),
        ("veteran_status", "VARCHAR(30)"),
        ("disability_status", "VARCHAR(20)"),
        # Extended Profile fields
        ("full_name", "VARCHAR(255)"),
        ("job_title", "VARCHAR(255)"),
        ("date_of_birth", "DATE"),
        # Preferences tab fields
        ("resume_email", "VARCHAR(255)"),
        ("language", "VARCHAR(10) DEFAULT 'en'"),
        ("base_resume_id", "INTEGER"),
        ("ai_model", "VARCHAR(50) DEFAULT 'gpt-4'"),
        # Auto Apply tab fields
        ("employment_status", "VARCHAR(50)"),
        ("job_titles", "JSON"),
        ("experience_level", "VARCHAR(50)"),
        ("industry", "VARCHAR(100)"),
        ("work_type", "VARCHAR(50)"),
        ("available_date", "DATE"),
        ("preferred_cities", "JSON"),
        ("remote_ok", "BOOLEAN DEFAULT FALSE"),
        ("hybrid_ok", "BOOLEAN DEFAULT FALSE"),
        ("drivers_license", "VARCHAR(10)"),
        ("security_clearance", "VARCHAR(10)"),
        ("apply_mode", "VARCHAR(20) DEFAULT 'hybrid'"),
        ("excluded_companies", "JSON"),
        # Job role selection
        ("job_roles", "JSON"),
        ("roles_confirmed_at", "TIMESTAMP"),
    ]

    with engine.connect() as conn:
        # Check existing columns
        try:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))
            existing_columns = {row[0] for row in result}
        except Exception:
            # SQLite fallback
            result = conn.execute(text("PRAGMA table_info(users)"))
            existing_columns = {row[1] for row in result}

        # Add missing columns
        for col_name, col_type in new_user_columns:
            if col_name not in existing_columns:
                try:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"Added column {col_name} to users table")
                except Exception as e:
                    logger.warning(f"Could not add column {col_name}: {e}")

        # Create user_documents table if not exists
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_documents (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    document_type VARCHAR(50) NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500),
                    file_size INTEGER,
                    mime_type VARCHAR(100),
                    content_text TEXT,
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_documents_user_id ON user_documents(user_id)"))
            logger.info("Created user_documents table")
        except Exception as e:
            logger.warning(f"Could not create user_documents table: {e}")

        # Add content_text column to user_documents if not exists
        try:
            # Check if column exists
            try:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user_documents'"))
                doc_columns = {row[0] for row in result}
            except Exception:
                result = conn.execute(text("PRAGMA table_info(user_documents)"))
                doc_columns = {row[1] for row in result}

            if 'content_text' not in doc_columns:
                conn.execute(text("ALTER TABLE user_documents ADD COLUMN content_text TEXT"))
                logger.info("Added content_text column to user_documents table")
        except Exception as e:
            logger.warning(f"Could not add content_text column: {e}")

        conn.commit()

        # Create admin_users table for internal admin access
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_users_username ON admin_users(username)"))
            logger.info("Created admin_users table")
        except Exception as e:
            logger.warning(f"Could not create admin_users table: {e}")

        # Seed initial admin user from environment variable
        admin_username = os.environ.get("INTERNAL_ADMIN_USER")
        admin_password = os.environ.get("INTERNAL_ADMIN_PASS")
        if admin_username and admin_password:
            try:
                # Check if admin exists
                result = conn.execute(text("SELECT id FROM admin_users WHERE username = :username"), {"username": admin_username})
                if not result.fetchone():
                    # Hash password
                    import hashlib
                    salt = os.environ.get("ADMIN_SALT", "cariara-internal-salt")
                    password_hash = hashlib.sha256(f"{salt}{admin_password}".encode()).hexdigest()
                    conn.execute(text(
                        "INSERT INTO admin_users (username, password_hash, name, is_active) VALUES (:username, :password_hash, :name, TRUE)"
                    ), {"username": admin_username, "password_hash": password_hash, "name": "Admin"})
                    logger.info(f"Created internal admin user: {admin_username}")
            except Exception as e:
                logger.warning(f"Could not seed admin user: {e}")

        # Extend job table columns for longer Eightfold URLs and titles.
        # ALTER COLUMN ... TYPE takes an ACCESS EXCLUSIVE lock (and may rewrite
        # the table), so only run it when the live column type actually differs.
        # PostgreSQL only - SQLite has no ALTER COLUMN TYPE.
        conn.commit()
        if conn.dialect.name == "postgresql":
            desired_job_column_types = {
                # column: (data_type, character_maximum_length, DDL type)
                "job_url": ("text", None, "TEXT"),
                "title": ("character varying", 500, "VARCHAR(500)"),
                "location": ("character varying", 500, "VARCHAR(500)"),
            }
            try:
                rows = conn.execute(text(
                    "SELECT column_name, data_type, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'jobs' AND table_schema = current_schema() "
                    "AND column_name IN ('job_url', 'title', 'location')"
                )).fetchall()
                current_types = {r[0]: (r[1], r[2]) for r in rows}
                for col, (data_type, max_len, ddl_type) in desired_job_column_types.items():
                    current = current_types.get(col)
                    if current is None or current == (data_type, max_len):
                        continue
                    # Never shrink: TEXT already satisfies any VARCHAR target.
                    if current[0] == "text":
                        continue
                    if (current[0] == data_type and max_len is not None
                            and current[1] is not None and current[1] >= max_len):
                        continue
                    conn.execute(text(f"ALTER TABLE jobs ALTER COLUMN {col} TYPE {ddl_type}"))
                    logger.info(f"Altered jobs.{col} from {current} to {ddl_type}")
            except Exception as e:
                logger.warning(f"Could not check/extend jobs column types: {e}")
                conn.rollback()

        conn.commit()

        # Add performance indexes for jobs table
        job_indexes = [
            ("ix_jobs_status", "jobs(status)"),
            ("ix_jobs_source", "jobs(source)"),
            ("ix_jobs_is_active", "jobs(is_active)"),
            ("ix_jobs_posted_date", "jobs(posted_date)"),
            ("ix_jobs_company_id", "jobs(company_id)"),
            ("ix_jobs_active_posted", "jobs(is_active, posted_date DESC)"),
        ]
        for idx_name, idx_cols in job_indexes:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_cols}"))
            except Exception as e:
                # Ignore if index already exists
                pass
        conn.commit()
        logger.info("Ensured job indexes exist")

        # Create auto-apply tables
        # Application answers table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS application_answers (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    question_pattern VARCHAR(500) NOT NULL,
                    question_category VARCHAR(50),
                    answer_text TEXT NOT NULL,
                    answer_type VARCHAR(20) DEFAULT 'text',
                    priority INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_application_answers_user_id ON application_answers(user_id)"))
            logger.info("Created application_answers table")
        except Exception as e:
            logger.warning(f"Could not create application_answers table: {e}")

        # Auto-apply config table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS auto_apply_configs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    enabled BOOLEAN DEFAULT FALSE,
                    default_resume_id INTEGER REFERENCES user_documents(id),
                    default_cover_letter_id INTEGER REFERENCES user_documents(id),
                    use_ai_cover_letter BOOLEAN DEFAULT TRUE,
                    daily_limit INTEGER DEFAULT 10,
                    applications_today INTEGER DEFAULT 0,
                    last_reset_date DATE,
                    min_relevance_score FLOAT DEFAULT 50.0,
                    excluded_companies TEXT,
                    supported_ats TEXT,
                    workday_email VARCHAR(255),
                    workday_password_encrypted TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_auto_apply_configs_user_id ON auto_apply_configs(user_id)"))
            logger.info("Created auto_apply_configs table")
        except Exception as e:
            logger.warning(f"Could not create auto_apply_configs table: {e}")

        # Add workday columns if missing (for existing tables)
        try:
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'auto_apply_configs'"))
            auto_apply_columns = {row[0] for row in result}

            if 'workday_email' not in auto_apply_columns:
                conn.execute(text("ALTER TABLE auto_apply_configs ADD COLUMN workday_email VARCHAR(255)"))
                logger.info("Added workday_email column to auto_apply_configs")

            if 'workday_password_encrypted' not in auto_apply_columns:
                conn.execute(text("ALTER TABLE auto_apply_configs ADD COLUMN workday_password_encrypted TEXT"))
                logger.info("Added workday_password_encrypted column to auto_apply_configs")
        except Exception as e:
            logger.warning(f"Could not add workday columns: {e}")

        # Application submissions table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS application_submissions (
                    id SERIAL PRIMARY KEY,
                    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    status VARCHAR(30) DEFAULT 'pending',
                    ats_type VARCHAR(50),
                    application_url VARCHAR(500),
                    resume_id INTEGER REFERENCES user_documents(id),
                    cover_letter_text TEXT,
                    ats_confirmation_id VARCHAR(255),
                    confirmation_screenshot VARCHAR(500),
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_application_submissions_user_id ON application_submissions(user_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_application_submissions_job_id ON application_submissions(job_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_application_submissions_status ON application_submissions(status)"))
            logger.info("Created application_submissions table")
        except Exception as e:
            logger.warning(f"Could not create application_submissions table: {e}")

        conn.commit()

        # Create scraper_configs table for scraper health tracking
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scraper_configs (
                    id SERIAL PRIMARY KEY,
                    company_slug VARCHAR(100) UNIQUE NOT NULL,
                    is_enabled BOOLEAN DEFAULT TRUE,
                    config_overrides JSONB DEFAULT '{}',
                    last_success_at TIMESTAMP,
                    last_failure_at TIMESTAMP,
                    consecutive_failures INTEGER DEFAULT 0,
                    total_runs INTEGER DEFAULT 0,
                    total_jobs_found INTEGER DEFAULT 0,
                    schedule_cron VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scraper_configs_company_slug ON scraper_configs(company_slug)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scraper_configs_is_enabled ON scraper_configs(is_enabled)"))
            logger.info("Created scraper_configs table")
        except Exception as e:
            logger.warning(f"Could not create scraper_configs table: {e}")

        conn.commit()

        # Add AI summary fields to jobs table
        try:
            # Check existing columns for jobs table
            try:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'jobs'"))
                job_columns = {row[0] for row in result}
            except Exception:
                result = conn.execute(text("PRAGMA table_info(jobs)"))
                job_columns = {row[1] for row in result}

            if 'ai_summary' not in job_columns:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_summary TEXT"))
                logger.info("Added ai_summary column to jobs table")

            if 'ai_tech_stack' not in job_columns:
                try:
                    # Try JSONB first (PostgreSQL)
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_tech_stack JSONB"))
                    logger.info("Added ai_tech_stack column to jobs table (JSONB)")
                except Exception:
                    # Fall back to TEXT for SQLite
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_tech_stack TEXT"))
                    logger.info("Added ai_tech_stack column to jobs table (TEXT)")
        except Exception as e:
            logger.warning(f"Could not add AI fields to jobs table: {e}")

        conn.commit()

        # Add new ingestion sources
        try:
            new_sources = [
                ('workday', 'orionadvisor:wd1:Orion_Careers', 'Orion Advisor'),
            ]
            for ats_type, slug, name in new_sources:
                # Check if source already exists
                try:
                    # PostgreSQL syntax
                    result = conn.execute(text(f"SELECT id FROM ingestion_sources WHERE ats_company_slug = '{slug}'"))
                except Exception:
                    # SQLite syntax
                    result = conn.execute(text(f"SELECT id FROM ingestion_sources WHERE ats_company_slug = '{slug}'"))

                if not result.fetchone():
                    conn.execute(text(f"""
                        INSERT INTO ingestion_sources (ats_type, ats_company_slug, company_name, is_active, job_count, created_at)
                        VALUES ('{ats_type}', '{slug}', '{name}', true, 0, CURRENT_TIMESTAMP)
                    """))
                    logger.info(f"Added ingestion source: {name}")
        except Exception as e:
            logger.warning(f"Could not add new ingestion sources: {e}")

        conn.commit()

        # Ensure first user is admin if no admin exists
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM users WHERE role = 'admin'"))
            admin_count = result.fetchone()[0]
            if admin_count == 0:
                # Promote the first user to admin
                result = conn.execute(text("SELECT id, email FROM users ORDER BY id LIMIT 1"))
                first_user = result.fetchone()
                if first_user:
                    conn.execute(text(f"UPDATE users SET role = 'admin' WHERE id = {first_user[0]}"))
                    conn.commit()
                    logger.info(f"Promoted first user {first_user[1]} to admin")
        except Exception as e:
            logger.warning(f"Could not check/promote admin user: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup - run migrations in background to not block health checks
    import threading

    from database import (
        engine,
        migration_lock,
        STARTUP_MIGRATIONS_LOCK_KEY,
        DOCUMENT_OWNERSHIP_LOCK_KEY,
    )

    def run_startup_migrations():
        # Several uvicorn workers boot at once; only one runs the DDL, the rest skip.
        try:
            with migration_lock(STARTUP_MIGRATIONS_LOCK_KEY) as acquired:
                if not acquired:
                    logger.info("Startup migrations running in another worker - skipping")
                    return
                create_tables()
                run_migrations()
                logger.info("Startup migrations completed")
        except Exception as e:
            logger.error(f"Startup migrations failed: {e}")

    # Run migrations in background thread so health checks pass immediately
    if not os.environ.get("SKIP_MIGRATIONS"):
        # Apply ownership changes before serving document requests. This one is
        # quick and idempotent, so wait for the lock rather than skipping it.
        from migrations.document_ownership import migrate_document_ownership
        with migration_lock(DOCUMENT_OWNERSHIP_LOCK_KEY, wait=True):
            with engine.begin() as conn:
                migrate_document_ownership(conn)
        migration_thread = threading.Thread(target=run_startup_migrations, daemon=True)
        migration_thread.start()
    else:
        logger.info("Skipping migrations (SKIP_MIGRATIONS=true)")

    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="JobTrails",
    version="1.0.0",
    description="Job tracking and discovery API with role-based relevance filtering",
    lifespan=lifespan
)

# Add middleware (order matters - first added is outermost)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# Observability middleware
app.add_middleware(ObservabilityMiddleware)
if metrics.enabled:
    app.add_middleware(MetricsMiddleware)

# Session middleware for OAuth state management
app.add_middleware(
    SessionMiddleware,
    secret_key=app_settings.jwt_secret_key,
    session_cookie="jobtrails_session",
    max_age=3600,  # 1 hour
    https_only=app_settings.is_production,  # Secure cookies in production
    same_site="lax",  # Allow OAuth redirects to include session cookie
)

# Only add API key auth if configured
if API_KEY:
    app.add_middleware(APIKeyAuthMiddleware)

class CatchAllExceptionMiddleware:
    """Turn unhandled exceptions into a JSON 500 *inside* CORSMiddleware.

    Starlette's @app.exception_handler(Exception) runs in ServerErrorMiddleware,
    which sits outside CORSMiddleware, so those 500s lack CORS headers and the
    browser reports a misleading "Failed to fetch"/CORS error. This pure ASGI
    middleware is registered just before CORSMiddleware (i.e. directly inside it).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            logger.error(
                "Unhandled exception on %s %s: %s\n%s",
                scope.get("method"), scope.get("path"), exc, traceback.format_exc(),
            )
            if response_started:
                raise
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)
            await response(scope, receive, send)


app.add_middleware(CatchAllExceptionMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Fallback for anything that escapes the middleware stack; adds CORS headers explicitly."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, exc,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    headers = {}
    origin = request.headers.get("origin")
    if origin and origin in ALLOWED_ORIGINS:
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return JSONResponse({"detail": "Internal server error"}, status_code=500, headers=headers)


# CORS - restricted to allowed origins (added last => outermost, so it also
# decorates the JSON 500s produced by CatchAllExceptionMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Content-Disposition", "Retry-After"],
)

# Include routers
app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(jobs.router)
app.include_router(companies.router)
app.include_router(contacts.router)
app.include_router(interviews.router)
app.include_router(notes.router)
app.include_router(documents.router)
app.include_router(ai.router)
app.include_router(analytics.router)
app.include_router(ingest.router)
app.include_router(settings.router)
app.include_router(users.router)
app.include_router(scrapers.router)
app.include_router(internal_auth.router)
# app.include_router(auto_apply.router)  # Disabled - users now apply manually
app.include_router(celery_management.router)
app.include_router(apify.router)
app.include_router(auto_heal.router)

# Static files for frontend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/")
def read_root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to JobTrails API",
        "version": "1.0.0",
        "docs": "/docs",
        "security": {
            "cors_origins": ALLOWED_ORIGINS,
            "rate_limit": f"{RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds",
            "api_key_required": bool(API_KEY),
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint - must respond quickly for Railway."""
    # Return immediately without checking external services
    # This ensures Railway health checks pass even if Redis/DB are slow
    return {"status": "healthy", "version": "2.1.2"}


@app.get("/health/db")
def db_health_check():
    """DB connectivity check — diagnoses Railway 500s on router routes."""
    from sqlalchemy import text
    from database import engine, SessionLocal
    result = {"engine_created": engine is not None, "db_url_tail": None, "ping": None, "error": None}
    try:
        from config import settings as _s
        url = _s.database_url
        result["db_url_tail"] = url.split("@")[-1] if "@" in url else url[:40]
    except Exception as e:
        result["error"] = f"config: {e}"
        return result
    if engine is None:
        result["error"] = "engine is None — DB failed to initialise"
        return result
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["ping"] = "ok"
    except Exception as e:
        result["ping"] = "failed"
        result["error"] = str(e)
    return result


@app.get("/health/redis")
def redis_health():
    """Detailed Redis health check."""
    return redis_service.health_check()


@app.get("/metrics")
def prometheus_metrics():
    """Prometheus metrics endpoint."""
    from starlette.responses import Response
    return Response(
        content=metrics.generate_metrics(),
        media_type="text/plain; charset=utf-8"
    )
# Deploy Fri Jan 30 17:49:31 PST 2026
