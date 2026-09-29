"""SentinelOne job scraper - Greenhouse API.

Greenhouse board renamed sentinelone -> sentinellabs (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import GreenhouseMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class SentinelOneScraper(GreenhouseMixin, HTTPScraper):
    """Scraper for SentinelOne careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="sentinelone",
        company_name="SentinelOne",
        careers_url="https://www.sentinelone.com/careers/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/sentinellabs/jobs"
