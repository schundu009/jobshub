"""Together AI job scraper - uses Greenhouse API (migrated from Ashby)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import GreenhouseMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class TogetherAIScraper(GreenhouseMixin, HTTPScraper):
    """Scraper for Together AI careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="togetherai",
        company_name="Together AI",
        careers_url="https://www.together.ai/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/togetherai/jobs"
