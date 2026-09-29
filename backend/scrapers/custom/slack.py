"""Slack job scraper - Workday API.

Greenhouse board gone; Slack now hires through Salesforce's Workday tenant, site 'Slack' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class SlackScraper(WorkdayMixin, HTTPScraper):
    """Scraper for Slack careers (Workday)."""

    config = ScraperConfig(
        company_slug="slack",
        company_name="Slack",
        careers_url="https://salesforce.wd12.myworkdayjobs.com/Slack",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/Slack/jobs"
