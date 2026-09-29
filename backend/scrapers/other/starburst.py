"""Starburst job scraper - Greenhouse API.

Greenhouse board renamed starburstdata -> starburst (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import GreenhouseMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class StarburstScraper(GreenhouseMixin, HTTPScraper):
    """Scraper for Starburst careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="starburst",
        company_name="Starburst",
        careers_url="https://www.starburst.io/careers/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/starburst/jobs"
