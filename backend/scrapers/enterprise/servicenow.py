"""
ServiceNow Jobs Scraper.

ServiceNow's Workday site (servicenow.wd1 .../ServiceNowCareers) returns 422;
careers.servicenow.com is backed by SmartRecruiters company "ServiceNow"
(verified 2026-09-29, ~700 postings).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import SmartRecruitersMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="enterprise")
class ServiceNowScraper(SmartRecruitersMixin, HTTPScraper):
    """Scraper for ServiceNow careers (SmartRecruiters)."""

    config = ScraperConfig(
        company_slug="servicenow",
        company_name="ServiceNow",
        careers_url="https://careers.servicenow.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
    )

    API_URL = "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings"
    COMPANY_ID = "ServiceNow"
