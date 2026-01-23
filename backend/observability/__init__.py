"""
Observability module for JobTrails Backend.

Provides:
- Structured JSON logging
- Prometheus metrics
- Request/response logging middleware
- Performance tracking
- Sentry error tracking
"""

from .logging_config import setup_logging, get_logger
from .metrics import metrics, MetricsMiddleware
from .middleware import ObservabilityMiddleware

__all__ = [
    "setup_logging",
    "get_logger",
    "metrics",
    "MetricsMiddleware",
    "ObservabilityMiddleware",
]
