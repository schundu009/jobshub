"""Postman job scraper - Workday API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import WorkdayMixin


# Moved Greenhouse -> Workday (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class PostmanScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Postman careers (Workday)."""

    config = ScraperConfig(
        company_slug="postman",
        company_name="Postman",
        careers_url="https://www.postman.com/company/careers/open-positions/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://postman.wd108.myworkdayjobs.com/wday/cxs/postman/careers/jobs"
