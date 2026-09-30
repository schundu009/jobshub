"""
Rippling Jobs Scraper.

Rippling hires through its own ATS (ats.rippling.com/rippling/jobs).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.rippling_ats_scrapers import RipplingATSMixin
from scrapers.registry import ScraperRegistry


# Moved to Rippling ATS (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class RipplingScraper(RipplingATSMixin, HTTPScraper):
    """Scraper for Rippling careers."""

    config = ScraperConfig(
        company_slug="rippling",
        company_name="Rippling",
        careers_url="https://www.rippling.com/careers/open-roles",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        request_timeout=30,
    )
    BOARD = "rippling"
