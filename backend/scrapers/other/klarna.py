"""
Klarna Jobs Scraper.

Klarna hires through Deel's ATS (jobs.deel.com/klarna).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.deel_ats_scrapers import DeelATSMixin
from scrapers.registry import ScraperRegistry


# Moved to Deel ATS (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class KlarnaScraper(DeelATSMixin, HTTPScraper):
    """Scraper for Klarna careers."""

    config = ScraperConfig(
        company_slug="klarna",
        company_name="Klarna",
        careers_url="https://jobs.deel.com/klarna",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        request_timeout=30,
    )
    BOARD = "klarna"
