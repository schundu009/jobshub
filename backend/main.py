"""
JobTrails API - Main Application Entry Point

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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from contextlib import asynccontextmanager
import os
import time
import logging
from collections import defaultdict
from typing import Optional

from database import create_tables
from routes import jobs, companies, contacts, interviews, notes, documents, ai, analytics, ingest, settings, users, scrapers, auth, oauth, internal_auth
from config import settings as app_settings
from services.redis_service import redis_service

logger = logging.getLogger(__name__)


# =============================================================================
# Security Configuration
# =============================================================================

# Allowed origins for CORS - configure via environment variable
# Format: comma-separated list of origins, e.g., "http://localhost:8000,https://myapp.com"
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,http://localhost:8001,http://127.0.0.1:3000,http://127.0.0.1:8000,http://127.0.0.1:8001,https://cariara.com,https://www.cariara.com,https://jobportal-ten-blush.vercel.app"
).split(",")

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
    "auth": {"limit": 10, "window": 60},       # 10 requests/minute for auth
    "auth_login": {"limit": 5, "window": 60},  # 5 login attempts/minute
    "api_read": {"limit": 300, "window": 60},  # 300 reads/minute
    "api_write": {"limit": 150, "window": 60}, # 150 writes/minute (for auto-save)
    "scraper": {"limit": 5, "window": 3600},   # 5 scraper triggers/hour
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
        """Check if Redis is available."""
        if not self._use_redis:
            return False
        try:
            return redis_service.ping()
        except Exception:
            self._use_redis = False
            logger.warning("Redis unavailable, falling back to in-memory rate limiting")
            return False

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

        # Try Redis first
        if self._check_redis():
            return redis_service.check_rate_limit(
                client_id, limit, window, endpoint_category
            )

        # Fallback to in-memory
        return self._in_memory_check(client_id, limit, window)

    def _in_memory_check(
        self,
        client_id: str,
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
            t for t in self._fallback_requests[client_id] if t > window_start
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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with endpoint-specific limits."""

    def _get_endpoint_category(self, path: str, method: str) -> str:
        """Determine the rate limit category for this endpoint."""
        # Auth endpoints
        if path.startswith("/auth/"):
            if path == "/auth/login":
                return "auth_login"
            return "auth"

        # Scraper endpoints
        if path.startswith("/api/scrapers") or path.startswith("/api/ingest"):
            if method == "POST":
                return "scraper"

        # API endpoints
        if path.startswith("/api/"):
            if method in ("POST", "PUT", "DELETE", "PATCH"):
                return "api_write"
            return "api_read"

        return "default"

    async def dispatch(self, request: Request, call_next):
        # Get client identifier
        # Prefer user ID from token, fall back to IP
        client_id = request.client.host if request.client else "unknown"

        # Try to get user ID from Authorization header for better tracking
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Extract user ID from token if possible (lightweight check)
            try:
                import base64
                import json
                token = auth_header[7:]
                # Decode payload without verification (just for user ID)
                payload_b64 = token.split(".")[1]
                # Add padding if needed
                padding = 4 - len(payload_b64) % 4
                if padding != 4:
                    payload_b64 += "=" * padding
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                if payload.get("sub"):
                    client_id = f"user:{payload['sub']}"
            except Exception:
                pass  # Fall back to IP

        # Get endpoint category
        path = request.url.path
        method = request.method
        category = self._get_endpoint_category(path, method)

        # Check rate limit
        is_allowed, remaining, retry_after = rate_limiter.is_allowed(client_id, category)

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
        if path in PUBLIC_ENDPOINTS or any(path.startswith(ep) for ep in PUBLIC_ENDPOINTS if ep.endswith("/")):
            return await call_next(request)

        # Skip auth for static files
        if path.startswith("/static"):
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
                    file_path VARCHAR(500) NOT NULL,
                    file_size INTEGER,
                    mime_type VARCHAR(100),
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_documents_user_id ON user_documents(user_id)"))
            logger.info("Created user_documents table")
        except Exception as e:
            logger.warning(f"Could not create user_documents table: {e}")

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

        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    create_tables()
    run_migrations()
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

# Session middleware for OAuth state management
app.add_middleware(
    SessionMiddleware,
    secret_key=app_settings.jwt_secret_key,
    session_cookie="jobtrails_session",
    max_age=3600,  # 1 hour
)

# Only add API key auth if configured
if API_KEY:
    app.add_middleware(APIKeyAuthMiddleware)

# CORS - restricted to allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
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
def health_check():
    """Health check endpoint."""
    redis_healthy = redis_service.ping()
    return {
        "status": "healthy" if redis_healthy else "degraded",
        "version": "1.0.0",
        "services": {
            "api": "healthy",
            "redis": "healthy" if redis_healthy else "unavailable",
        }
    }


@app.get("/health/redis")
def redis_health():
    """Detailed Redis health check."""
    return redis_service.health_check()
