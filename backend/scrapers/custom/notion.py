"""Notion job scraper - Ashby API (migrated from Greenhouse)."""

from scrapers.base import HTTPScraper, AshbyMixin, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class NotionScraper(AshbyMixin, HTTPScraper):
    """Scraper for Notion careers (Ashby)."""

    config = ScraperConfig(
        company_slug="notion",
        company_name="Notion",
        careers_url="https://www.notion.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/notion"
