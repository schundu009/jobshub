"""Visa job scraper - Workday API.

careers.visa.com no longer resolves; Visa hires via Workday visa.wd5, site 'Visa'
(verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="finance")
class VisaScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Visa careers (Workday)."""

    config = ScraperConfig(
        company_slug="visa",
        company_name="Visa",
        careers_url="https://visa.wd5.myworkdayjobs.com/Visa",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        max_pages=10,
    )

    API_URL = "https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs"
