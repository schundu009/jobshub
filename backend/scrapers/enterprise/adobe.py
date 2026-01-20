"""
Adobe Jobs Scraper.

Uses Playwright to scrape Adobe's Workday careers page with job descriptions.
"""

from scrapers.base import PlaywrightScraper, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry
from scrapers.enterprise.workday_scrapers import WorkdayPlaywrightMixin


@ScraperRegistry.register(category="enterprise")
class AdobeScraper(WorkdayPlaywrightMixin, PlaywrightScraper):
    """Scraper for Adobe careers using Playwright with Workday mixin."""

    config = ScraperConfig(
        company_slug="adobe",
        company_name="Adobe",
        careers_url="https://adobe.wd5.myworkdayjobs.com/external_experienced",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        max_pages=10,
        page_timeout=45,
    )

    BASE_URL = "https://adobe.wd5.myworkdayjobs.com/external_experienced"
