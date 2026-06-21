"""
Prometheus Metrics for JobTrails Backend.

Exposes metrics at /metrics endpoint for scraping by Prometheus.
"""

import time
from typing import Callable
from functools import wraps

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        multiprocess,
        REGISTRY,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class Metrics:
    """Application metrics using Prometheus."""

    def __init__(self):
        if not PROMETHEUS_AVAILABLE:
            self._enabled = False
            return

        self._enabled = True

        # HTTP Request metrics
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"]
        )

        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
        )

        self.http_requests_in_progress = Gauge(
            "http_requests_in_progress",
            "Number of HTTP requests in progress",
            ["method", "endpoint"]
        )

        # Database metrics
        self.db_query_duration_seconds = Histogram(
            "db_query_duration_seconds",
            "Database query duration in seconds",
            ["operation", "table"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
        )

        self.db_connections_active = Gauge(
            "db_connections_active",
            "Number of active database connections"
        )

        # Cache metrics
        self.cache_hits_total = Counter(
            "cache_hits_total",
            "Total cache hits",
            ["cache_type"]
        )

        self.cache_misses_total = Counter(
            "cache_misses_total",
            "Total cache misses",
            ["cache_type"]
        )

        # Job scraper metrics
        self.scraper_runs_total = Counter(
            "scraper_runs_total",
            "Total scraper runs",
            ["company", "status"]
        )

        self.scraper_jobs_found = Gauge(
            "scraper_jobs_found",
            "Number of jobs found in last scraper run",
            ["company"]
        )

        self.scraper_duration_seconds = Histogram(
            "scraper_duration_seconds",
            "Scraper run duration in seconds",
            ["company"],
            buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
        )

        # Business metrics
        self.jobs_total = Gauge(
            "jobs_total",
            "Total number of jobs in database",
            ["status"]
        )

        self.companies_total = Gauge(
            "companies_total",
            "Total number of companies"
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float
    ) -> None:
        """Record HTTP request metrics."""
        if not self._enabled:
            return

        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()

        self.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def record_db_query(
        self,
        operation: str,
        table: str,
        duration: float
    ) -> None:
        """Record database query metrics."""
        if not self._enabled:
            return

        self.db_query_duration_seconds.labels(
            operation=operation,
            table=table
        ).observe(duration)

    def record_cache_hit(self, cache_type: str = "redis") -> None:
        """Record cache hit."""
        if not self._enabled:
            return
        self.cache_hits_total.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str = "redis") -> None:
        """Record cache miss."""
        if not self._enabled:
            return
        self.cache_misses_total.labels(cache_type=cache_type).inc()

    def record_scraper_run(
        self,
        company: str,
        status: str,
        jobs_found: int,
        duration: float
    ) -> None:
        """Record scraper run metrics."""
        if not self._enabled:
            return

        self.scraper_runs_total.labels(company=company, status=status).inc()
        self.scraper_jobs_found.labels(company=company).set(jobs_found)
        self.scraper_duration_seconds.labels(company=company).observe(duration)

    def update_job_counts(self, status_counts: dict) -> None:
        """Update job count gauges."""
        if not self._enabled:
            return

        for status, count in status_counts.items():
            self.jobs_total.labels(status=status).set(count)

    def update_company_count(self, count: int) -> None:
        """Update company count gauge."""
        if not self._enabled:
            return
        self.companies_total.set(count)

    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics output."""
        if not self._enabled:
            return b"# Prometheus metrics not available"
        return generate_latest(REGISTRY)


# Global metrics instance
metrics = Metrics()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP request metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not metrics.enabled:
            return await call_next(request)

        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            return await call_next(request)

        # Get endpoint pattern for better grouping
        endpoint = self._get_endpoint_pattern(request)
        method = request.method

        # Track in-progress requests
        metrics.http_requests_in_progress.labels(
            method=method,
            endpoint=endpoint
        ).inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start_time

            metrics.http_requests_in_progress.labels(
                method=method,
                endpoint=endpoint
            ).dec()

            metrics.record_request(method, endpoint, status_code, duration)

        return response

    def _get_endpoint_pattern(self, request: Request) -> str:
        """Get the route pattern instead of the actual path for better grouping."""
        try:
            for route in request.app.routes:
                match, _ = route.matches(request.scope)
                if match == Match.FULL:
                    return route.path
        except Exception:
            pass
        import re
        return re.sub(r'/\d+', '/{id}', request.url.path)


def track_time(metric_name: str = None):
    """Decorator to track function execution time."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                # Log slow operations
                if duration > 1.0:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Slow operation: {func.__name__} took {duration:.2f}s"
                    )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                if duration > 1.0:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Slow operation: {func.__name__} took {duration:.2f}s"
                    )

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
