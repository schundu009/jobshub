"""Expedia Group job scraper - Workday API.

careers.expediagroup.com/api/jobs never existed as JSON; careers.expediagroup.com links to
Workday tenant expedia.wd108, site 'search' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class ExpediaScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Expedia Group careers (Workday)."""

    config = ScraperConfig(
        company_slug="expedia",
        company_name="Expedia Group",
        careers_url="https://expedia.wd108.myworkdayjobs.com/search",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        max_pages=10,
    )

    API_URL = "https://expedia.wd108.myworkdayjobs.com/wday/cxs/expedia/search/jobs"
