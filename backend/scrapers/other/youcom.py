"""You.com job scraper - Greenhouse API.

Moved Lever -> Greenhouse board 'youcom' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import GreenhouseMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class YouComScraper(GreenhouseMixin, HTTPScraper):
    """Scraper for You.com careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="youcom",
        company_name="You.com",
        careers_url="https://you.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/youcom/jobs"
