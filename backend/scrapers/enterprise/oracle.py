"""
Oracle Jobs Scraper.

Uses Oracle's careers API.
"""

from datetime import datetime
from typing import Optional

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="enterprise")
class OracleScraper(HTTPScraper):
    """Scraper for Oracle careers."""

    config = ScraperConfig(
        company_slug="oracle",
        company_name="Oracle",
        careers_url="https://careers.oracle.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Oracle careers API."""
        all_jobs = []
        offset = 0

        while offset < self.config.max_pages * self.config.page_size:
            params = {
                "onlyData": "true",
                "expand": "requisitionList.secondaryLocations,requisitionList.primaryLocation,requisitionList.workLocation",
                "finder": f"findReqs;siteNumber=CX_1,facetsList=,limit={self.config.page_size},offset={offset},sortBy=POSTING_DATES_DESC",
            }

            try:
                data = await self.fetch_json(self.config.api_url, params=params)

                items = data.get("items", [])
                if not items:
                    break

                requisitions = items[0].get("requisitionList", []) if items else []
                if not requisitions:
                    break

                for job_data in requisitions:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

                if len(requisitions) < self.config.page_size:
                    break

                offset += self.config.page_size

            except Exception as e:
                self.logger.error(f"Error fetching offset {offset}: {e}")
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            pages_scraped=(offset // self.config.page_size) + 1,
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse Oracle job data."""
        try:
            job_id = raw.get("Id", "") or raw.get("RequisitionNumber", "")

            # Get location
            primary_loc = raw.get("primaryLocation", {}) or {}
            location = primary_loc.get("LocationName", "") or raw.get("PrimaryLocationCountry", "")

            # Build job URL
            job_url = f"https://careers.oracle.com/jobs/#en/sites/jobsearch/job/{job_id}"

            return ScrapedJob(
                title=raw.get("Title", ""),
                location=location,
                job_url=job_url,
                external_job_id=str(job_id),
                job_description=raw.get("ShortDescriptionStr", ""),
                department=raw.get("OrganizationName", ""),
                posted_date=self.parse_date(raw.get("PostedDate", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
