"""
Apify-based scrapers for job boards.

These scrapers use Apify's cloud platform to scrape jobs from:
- LinkedIn Jobs
- Indeed Jobs
- Glassdoor Jobs

Benefits:
- Cloud-based, no local browser needed
- Built-in proxy rotation
- Handles anti-bot measures
- Independent of Celery workers
"""

from .base import ApifyScraper, ApifyScraperConfig
from .linkedin import LinkedInJobsScraper
from .indeed import IndeedJobsScraper

__all__ = [
    "ApifyScraper",
    "ApifyScraperConfig",
    "LinkedInJobsScraper",
    "IndeedJobsScraper",
]
