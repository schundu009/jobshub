"""Cohere job scraper - Ashby API.

Moved Lever -> Ashby (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import AshbyMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class CohereScraper(AshbyMixin, HTTPScraper):
    """Scraper for Cohere careers (Ashby)."""

    config = ScraperConfig(
        company_slug="cohere",
        company_name="Cohere",
        careers_url="https://cohere.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/cohere"
