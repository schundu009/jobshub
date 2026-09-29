"""
Disney Jobs Scraper.

jobs.disneycareers.com is a Radancy front-end with no JSON API (/api/jobs
redirects to the HTML home page). The underlying ATS is Workday tenant
"disney", site "disneycareer" (verified 2026-09-29, ~600 postings).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class DisneyScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Disney careers (Workday)."""

    config = ScraperConfig(
        company_slug="disney",
        company_name="The Walt Disney Company",
        careers_url="https://jobs.disneycareers.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
    )

    API_URL = "https://disney.wd5.myworkdayjobs.com/wday/cxs/disney/disneycareer/jobs"
