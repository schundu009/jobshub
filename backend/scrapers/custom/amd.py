"""AMD - careers.amd.com (iCIMS Jibe careers site, its own /api/jobs JSON).

The careers-home search page reads GET https://careers.amd.com/api/jobs?page=N&limit=100
(~1,300 postings, full descriptions). Apply links go to *-amd.icims.com.
Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import JibeMixin, OwnSiteScraper
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class AMDScraper(JibeMixin, OwnSiteScraper):
    config = ScraperConfig(
        company_slug="amd",
        company_name="AMD",
        careers_url="https://careers.amd.com/careers-home/jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    BASE_URL = "https://careers.amd.com"
