"""
Auto-apply services for automated job application submission.

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
