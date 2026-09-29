"""Comcast job scraper - Workday API.

Uses the shared WorkdayMixin (page size 20, relative postedOn dates, correct job URLs).
The previous bespoke copy sent limit=50 (Workday answers HTTP 400) and failed to parse
"Posted N Days Ago" dates, so it returned 0 jobs. Verified 2026-09-29. Comcast moved from wd5 to wd115.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class ComcastScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Comcast careers (Workday)."""

    config = ScraperConfig(
        company_slug="comcast",
        company_name="Comcast",
        careers_url="https://comcast.wd115.myworkdayjobs.com/Comcast_Careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=10,
    )

    API_URL = "https://comcast.wd115.myworkdayjobs.com/wday/cxs/comcast/Comcast_Careers/jobs"
