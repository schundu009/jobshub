"""Deel job scraper - Deel's own ATS (jobs.deel.com/deel -> www.deel.com/careers)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.deel_ats_scrapers import DeelATSMixin
from scrapers.registry import ScraperRegistry


# Moved to Deel ATS (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class DeelScraper(DeelATSMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="deel", company_name="Deel", careers_url="https://www.deel.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30, max_pages=10, request_timeout=30,
    )
    BOARD = "deel"
