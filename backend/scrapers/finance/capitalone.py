"""Capital One job scraper - Workday API.

The old capitalonecareers.com/api/jobs endpoint no longer returns JSON jobs; Capital One
(and Discover, which it absorbed) hire through Workday tenant 'capitalone' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="finance")
class CapitalOneScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Capital One careers (Workday)."""

    config = ScraperConfig(
        company_slug="capitalone",
        company_name="Capital One",
        careers_url="https://capitalone.wd12.myworkdayjobs.com/Capital_One",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        max_pages=10,
    )

    API_URL = "https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs"
