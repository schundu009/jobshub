"""
Oracle Jobs Scraper.

Uses Oracle Recruiting Cloud (HCM) CandidateExperience REST API. The same
OracleHCMMixin is reused by other Oracle-HCM tenants (e.g. JPMorgan Chase).
"""

import asyncio
from typing import Optional

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.registry import ScraperRegistry


class OracleHCMMixin:
    """
    Oracle Recruiting Cloud: GET {HCM_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions

    Subclasses set HCM_HOST, SITE_NUMBER, and optionally MAX_JOBS / JOB_URL_BASE.
    Note: `expand` must be exactly "requisitionList.secondaryLocations"; adding
    primaryLocation/workLocation makes the API answer HTTP 400.
    """

    HCM_HOST: str = ""
    SITE_NUMBER: str = ""
    PAGE_SIZE = 200   # API max observed; ~3.5s per page
    MAX_JOBS = 2400   # keep each run well under the 120s celery soft limit
    JOB_URL_BASE: Optional[str] = None

    @property
    def hcm_api_url(self) -> str:
        return f"https://{self.HCM_HOST}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    def hcm_job_url(self, job_id: str) -> str:
        base = self.JOB_URL_BASE or (
            f"https://{self.HCM_HOST}/hcmUI/CandidateExperience/en/sites/{self.SITE_NUMBER}/job/"
        )
        return f"{base}{job_id}"

    async def scrape(self) -> ScrapeResult:
        all_jobs = []
        offset = 0
        pages = 0
        total = None

        while offset < self.MAX_JOBS:
            params = {
                "onlyData": "true",
                "expand": "requisitionList.secondaryLocations",
                "finder": (
                    f"findReqs;siteNumber={self.SITE_NUMBER},facetsList=,"
                    f"limit={self.PAGE_SIZE},offset={offset},sortBy=POSTING_DATES_DESC"
                ),
            }
            data = await self.fetch_json(self.hcm_api_url, params=params)
            items = self.expect_list(data, "items")
            if not items:
                if offset == 0:
                    raise UnexpectedResponseError("Oracle HCM returned no search items")
                break
            search = items[0]
            if total is None:
                total = search.get("TotalJobsCount") or 0
            reqs = self.expect_list(search, "requisitionList")
            pages += 1
            if not reqs:
                break
            all_jobs.extend(self.parse_all(reqs))
            offset += self.PAGE_SIZE
            if len(reqs) < self.PAGE_SIZE or offset >= total:
                break
            await asyncio.sleep(0.2)

        return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=pages)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("Id", "") or "")
            if not job_id:
                return None
            location = raw.get("PrimaryLocation") or raw.get("PrimaryLocationCountry") or ""
            return ScrapedJob(
                title=raw.get("Title", ""),
                location=location,
                job_url=self.hcm_job_url(job_id),
                external_job_id=job_id,
                job_description=raw.get("ShortDescriptionStr", ""),
                department=raw.get("JobFamily") or raw.get("Department") or "",
                posted_date=self.parse_date(raw.get("PostedDate", "")),
                remote_type=(raw.get("WorkplaceTypeCode") or None),
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None


@ScraperRegistry.register(category="enterprise")
class OracleScraper(OracleHCMMixin, HTTPScraper):
    """Scraper for Oracle careers."""

    config = ScraperConfig(
        company_slug="oracle",
        company_name="Oracle",
        careers_url="https://careers.oracle.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
    )

    HCM_HOST = "eeho.fa.us2.oraclecloud.com"
    SITE_NUMBER = "CX_45001"
    JOB_URL_BASE = "https://careers.oracle.com/en/sites/jobsearch/job/"
