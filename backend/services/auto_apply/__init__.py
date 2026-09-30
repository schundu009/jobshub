"""
Legacy headless Playwright submitters (Greenhouse, Lever, Workday).

NOT wired to any route or Celery task. Cariara Auto Apply (services/apply,
routes/apply.py) never submits applications server-side; submission is done
by the customer or the Cariara browser extension (Phase 2).

Supports:
- Greenhouse ATS
- Lever ATS
"""

from .base import BaseApplicant, ApplyResult
from .greenhouse import GreenhouseApplicant
from .lever import LeverApplicant

__all__ = [
    "BaseApplicant",
    "ApplyResult",
    "GreenhouseApplicant",
    "LeverApplicant",
]
