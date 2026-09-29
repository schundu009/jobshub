"""Etsy job scraper - Workday API.

Moved Greenhouse -> Workday (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class EtsyScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Etsy careers (Workday)."""

    config = ScraperConfig(
        company_slug="etsy",
        company_name="Etsy",
        careers_url="https://careers.etsy.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=10,
    )

    API_URL = "https://etsy.wd5.myworkdayjobs.com/wday/cxs/etsy/Etsy_Careers/jobs"
