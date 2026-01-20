"""Nvidia job scraper - Playwright-based with Workday mixin."""

from scrapers.base import PlaywrightScraper, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry
from scrapers.enterprise.workday_scrapers import WorkdayPlaywrightMixin


@ScraperRegistry.register(category="custom")
class NvidiaScraper(WorkdayPlaywrightMixin, PlaywrightScraper):
    """Scraper for Nvidia careers using Playwright with Workday mixin."""

    config = ScraperConfig(
        company_slug="nvidia",
        company_name="Nvidia",
        careers_url="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        max_pages=10,
        page_timeout=45,
    )

    BASE_URL = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
