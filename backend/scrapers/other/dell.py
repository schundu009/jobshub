"""
Dell Jobs Scraper.

jobs.dell.com (Akamai 403 for scripts) now redirects to Dell's Oracle
Recruiting Cloud site: enterpriseplatform.dell.com/hcmUI/CandidateExperience
(tenant iawmqy.fa.ocs.oraclecloud.com, site CX_1001).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.oracle import OracleHCMMixin
from scrapers.registry import ScraperRegistry


# Moved to Oracle HCM (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class DellScraper(OracleHCMMixin, HTTPScraper):
    """Scraper for Dell careers (Oracle Recruiting Cloud)."""

    config = ScraperConfig(
        company_slug="dell",
        company_name="Dell Technologies",
        careers_url="https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/CX_1001",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
    )

    HCM_HOST = "enterpriseplatform.dell.com"
    SITE_NUMBER = "CX_1001"
    MAX_JOBS = 1500
