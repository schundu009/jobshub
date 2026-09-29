"""Verizon job scraper - Workday API.

verizon.com/careers/api/jobs returns no JSON; Verizon hires via Workday verizon.wd12,
site 'verizon-careers' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class VerizonScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Verizon careers (Workday)."""

    config = ScraperConfig(
        company_slug="verizon",
        company_name="Verizon",
        careers_url="https://verizon.wd12.myworkdayjobs.com/verizon-careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        max_pages=10,
    )

    API_URL = "https://verizon.wd12.myworkdayjobs.com/wday/cxs/verizon/verizon-careers/jobs"
