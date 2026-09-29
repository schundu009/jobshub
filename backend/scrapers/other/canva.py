"""Canva job scraper - SmartRecruiters API.

Moved Greenhouse -> SmartRecruiters (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import SmartRecruitersMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class CanvaScraper(SmartRecruitersMixin, HTTPScraper):
    """Scraper for Canva careers (SmartRecruiters)."""

    config = ScraperConfig(
        company_slug="canva",
        company_name="Canva",
        careers_url="https://www.canva.com/careers/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=10,
    )

    API_URL = "https://api.smartrecruiters.com/v1/companies/canva/postings"
    COMPANY_ID = "canva"
