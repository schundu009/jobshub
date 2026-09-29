"""Snowflake job scraper - Ashby API.

Moved Greenhouse -> Ashby (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import AshbyMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class SnowflakeScraper(AshbyMixin, HTTPScraper):
    """Scraper for Snowflake careers (Ashby)."""

    config = ScraperConfig(
        company_slug="snowflake",
        company_name="Snowflake",
        careers_url="https://careers.snowflake.com",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/snowflake"
