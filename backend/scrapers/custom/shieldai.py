"""Shield AI job scraper - Lever API.

Moved Greenhouse -> Lever (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import LeverMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class ShieldAIScraper(LeverMixin, HTTPScraper):
    """Scraper for Shield AI careers (Lever)."""

    config = ScraperConfig(
        company_slug="shieldai",
        company_name="Shield AI",
        careers_url="https://jobs.lever.co/shieldai",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.lever.co/v0/postings/shieldai?mode=json"
