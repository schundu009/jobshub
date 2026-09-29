"""Zendesk job scraper - Workday API.

Moved Greenhouse -> Workday (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class ZendeskScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Zendesk careers (Workday)."""

    config = ScraperConfig(
        company_slug="zendesk",
        company_name="Zendesk",
        careers_url="https://zendesk.wd1.myworkdayjobs.com/zendesk",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://zendesk.wd1.myworkdayjobs.com/wday/cxs/zendesk/zendesk/jobs"
