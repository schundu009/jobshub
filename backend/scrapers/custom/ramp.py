"""Ramp job scraper - Ashby API (migrated from Greenhouse)."""

from scrapers.base import HTTPScraper, AshbyMixin, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class RampScraper(AshbyMixin, HTTPScraper):
    """Scraper for Ramp careers (Ashby)."""

    config = ScraperConfig(
        company_slug="ramp",
        company_name="Ramp",
        careers_url="https://ramp.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/ramp"
