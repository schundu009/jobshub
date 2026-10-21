"""Keysight Technologies - jobs.keysight.com (iCIMS Jibe careers site, its own /api/jobs JSON).

The search page reads GET https://jobs.keysight.com/api/jobs?page=N&limit=100
(~739 postings, full descriptions). Apply links go to globalcareers-keysight.icims.com.
Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import JibeMixin, OwnSiteScraper
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class KeysightScraper(JibeMixin, OwnSiteScraper):
    config = ScraperConfig(
        company_slug="keysight",
        company_name="Keysight Technologies",
        careers_url="https://jobs.keysight.com/careers-home/jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    BASE_URL = "https://jobs.keysight.com"
