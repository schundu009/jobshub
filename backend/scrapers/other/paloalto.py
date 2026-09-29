"""Palo Alto Networks job scraper - Workday API.

Uses the shared WorkdayMixin (page size 20, relative postedOn dates, correct job URLs).
The previous bespoke copy sent limit=50 (Workday answers HTTP 400) and failed to parse
"Posted N Days Ago" dates, so it returned 0 jobs. Verified 2026-09-29.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class PaloAltoNetworksScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Palo Alto Networks careers (Workday)."""

    config = ScraperConfig(
        company_slug="paloaltonetworks",
        company_name="Palo Alto Networks",
        careers_url="https://jobs.paloaltonetworks.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=10,
    )

    API_URL = "https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/panwexternalcareers/jobs"
