"""Glean job scraper - Ashby API (migrated from Greenhouse)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import AshbyMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class GleanScraper(AshbyMixin, HTTPScraper):
    """Scraper for Glean careers (Ashby)."""

    config = ScraperConfig(
        company_slug="glean",
        company_name="Glean",
        careers_url="https://www.glean.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/glean"
