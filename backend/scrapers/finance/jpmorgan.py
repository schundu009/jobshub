"""
JPMorgan Chase Jobs Scraper.

JPMorgan Chase hires through Oracle Recruiting Cloud (tenant jpmc.fa.oraclecloud.com,
site CX_1001). The old careers.jpmorgan.com/api/v2/jobs endpoint now serves HTML.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.oracle import OracleHCMMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="finance")
class JPMorganScraper(OracleHCMMixin, HTTPScraper):
    """Scraper for JPMorgan Chase careers (Oracle HCM)."""

    config = ScraperConfig(
        company_slug="jpmorgan",
        company_name="JPMorgan Chase",
        careers_url="https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
    )

    HCM_HOST = "jpmc.fa.oraclecloud.com"
    SITE_NUMBER = "CX_1001"
    # ~7.5k openings; newest 3000 keeps the run ~50s (under the 120s soft limit)
    MAX_JOBS = 3000
