"""ContextualAI job scraper - uses Greenhouse API (migrated from Ashby)."""

from scrapers.base import HTTPScraper, GreenhouseMixin, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class ContextualAIScraper(GreenhouseMixin, HTTPScraper):
    """Scraper for ContextualAI careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="contextualai",
        company_name="Contextual AI",
        careers_url="https://contextual.ai/careers/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/contextualai/jobs"
