"""Garmin - careers.garmin.com (iCIMS Jibe careers site, its own /api/jobs JSON).

The search page reads GET https://careers.garmin.com/api/jobs?page=N&limit=100
(~434 postings, full descriptions). Apply links go to careers-garmin.icims.com.
Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import JibeMixin, OwnSiteScraper
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class GarminScraper(JibeMixin, OwnSiteScraper):
    config = ScraperConfig(
        company_slug="garmin",
        company_name="Garmin",
        careers_url="https://careers.garmin.com/careers-home/jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    BASE_URL = "https://careers.garmin.com"
