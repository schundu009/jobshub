"""
Observability Middleware.

Provides request/response logging with timing, correlation IDs, and error tracking.
"""

import time
import uuid
import logging
import os
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request/response observability.

    Features:
    - Request correlation IDs
    - Request/response logging
    - Performance timing
    - Slow request warnings
    """

    SLOW_REQUEST_THRESHOLD = 2.0  # seconds

    # Paths to skip logging (health checks, metrics, static files)
    SKIP_PATHS = {"/health", "/health/redis", "/metrics", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for certain paths
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]

        # Store in request state for use in handlers
        request.state.correlation_id = correlation_id

        # Extract request info
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:100]

        # Log request start
        logger.info(
            f"[{correlation_id}] --> {method} {path}",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "query": query,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "event": "request_start",
            }
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
            error = None
        except Exception as e:
            status_code = 500
            error = str(e)
            logger.exception(
                f"[{correlation_id}] Request failed: {e}",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "error": error,
                    "event": "request_error",
                }
            )
            raise

        duration = time.perf_counter() - start_time
        duration_ms = round(duration * 1000, 2)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Log level based on status code and duration
        log_level = logging.INFO
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        elif duration > self.SLOW_REQUEST_THRESHOLD:
            log_level = logging.WARNING

        # Log request completion
        log_message = f"[{correlation_id}] <-- {method} {path} {status_code} {duration_ms}ms"
        if duration > self.SLOW_REQUEST_THRESHOLD:
            log_message += " [SLOW]"

        logger.log(
            log_level,
            log_message,
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "event": "request_complete",
                "slow": duration > self.SLOW_REQUEST_THRESHOLD,
            }
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, handling proxies."""
        # Check for forwarded headers (when behind proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct client
        if request.client:
            return request.client.host

        return "unknown"


class SentryMiddleware:
    """
    Sentry integration middleware.

    Captures errors and adds context to Sentry events.
    """

    def __init__(self, app, dsn: Optional[str] = None):
        self.app = app
        self.enabled = False

        if dsn:
            try:
                import sentry_sdk
                from sentry_sdk.integrations.fastapi import FastApiIntegration
                from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
                from sentry_sdk.integrations.redis import RedisIntegration

                sentry_sdk.init(
                    dsn=dsn,
                    integrations=[
                        FastApiIntegration(transaction_style="endpoint"),
                        SqlalchemyIntegration(),
                        RedisIntegration(),
                    ],
                    traces_sample_rate=0.1,  # 10% of transactions
                    profiles_sample_rate=0.1,  # 10% of profiled transactions
                    environment=os.getenv("ENV", "development"),
                    send_default_pii=False,
                )
                self.enabled = True
                logger.info("Sentry initialized successfully")
            except ImportError:
                logger.warning("Sentry SDK not installed, error tracking disabled")
            except Exception as e:
                logger.error(f"Failed to initialize Sentry: {e}")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.enabled:
            try:
                import sentry_sdk
                with sentry_sdk.configure_scope() as sentry_scope:
                    # Add request context
                    sentry_scope.set_tag("path", scope.get("path", "unknown"))
                    await self.app(scope, receive, send)
            except Exception as e:
                sentry_sdk.capture_exception(e)
                raise
        else:
            await self.app(scope, receive, send)
