"""Zillow job scraper - Workday API.

Uses the shared WorkdayMixin (page size 20, relative postedOn dates, correct job URLs).
The previous bespoke copy sent limit=50 (Workday answers HTTP 400) and failed to parse
"Posted N Days Ago" dates, so it returned 0 jobs. Verified 2026-09-29.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class ZillowScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Zillow careers (Workday)."""

    config = ScraperConfig(
        company_slug="zillow",
        company_name="Zillow",
        careers_url="https://www.zillow.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://zillow.wd5.myworkdayjobs.com/wday/cxs/zillow/Zillow_Group_External/jobs"
