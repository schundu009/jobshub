"""HPE job scraper - Workday API.

Uses the shared WorkdayMixin (page size 20, relative postedOn dates, correct job URLs).
The previous bespoke copy sent limit=50 (Workday answers HTTP 400) and failed to parse
"Posted N Days Ago" dates, so it returned 0 jobs. Verified 2026-09-29.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class HPEScraper(WorkdayMixin, HTTPScraper):
    """Scraper for HPE careers (Workday)."""

    config = ScraperConfig(
        company_slug="hpe",
        company_name="HPE",
        careers_url="https://careers.hpe.com/us/en/search-results",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=10,
    )

    API_URL = "https://hpe.wd5.myworkdayjobs.com/wday/cxs/hpe/Jobsathpe/jobs"
