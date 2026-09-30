"""
SAP Jobs Scraper.

jobs.sap.com is now a Next.js site behind a Cloudflare challenge, backed by
SmartRecruiters (SAP acquired SmartRecruiters in 2025). Postings are published
under the SmartRecruiters company identifier "SAPITBusinessSysteme"; the public
posting API's totalFound matches the site's job count.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import SmartRecruitersMixin
from scrapers.registry import ScraperRegistry


# Moved to SmartRecruiters (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class SAPScraper(SmartRecruitersMixin, HTTPScraper):
    """Scraper for SAP careers (SmartRecruiters)."""

    config = ScraperConfig(
        company_slug="sap",
        company_name="SAP",
        careers_url="https://jobs.sap.com/en/jobs/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
    )

    API_URL = "https://api.smartrecruiters.com/v1/companies/SAPITBusinessSysteme/postings"
    COMPANY_ID = "SAPITBusinessSysteme"
