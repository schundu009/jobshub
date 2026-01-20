"""
ServiceNow Jobs Scraper.

Uses ServiceNow's Workday-based careers API.
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
class ServiceNowScraper(HTTPScraper):
    """Scraper for ServiceNow careers."""

    config = ScraperConfig(
        company_slug="servicenow",
        company_name="ServiceNow",
        careers_url="https://careers.servicenow.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://servicenow.wd1.myworkdayjobs.com/wday/cxs/servicenow/ServiceNowCareers/jobs",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape ServiceNow Workday API."""
        all_jobs = []
        offset = 0

        while offset < self.config.max_pages * self.config.page_size:
            payload = {
                "appliedFacets": {},
                "limit": self.config.page_size,
                "offset": offset,
                "searchText": "engineer",
            }

            try:
                data = await self.fetch_json(
                    self.config.api_url,
                    method="POST",
                    json_data=payload,
                )

                postings = data.get("jobPostings", [])
                if not postings:
                    break

                for job_data in postings:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

                total = data.get("total", 0)
                if offset + len(postings) >= total:
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
        """Parse ServiceNow Workday job data."""
        try:
            external_path = raw.get("externalPath", "")
            job_id = external_path.split("/")[-1] if external_path else ""

            job_url = f"https://servicenow.wd1.myworkdayjobs.com/en-US/ServiceNowCareers{external_path}"

            return ScrapedJob(
                title=raw.get("title", ""),
                location=raw.get("locationsText", ""),
                job_url=job_url,
                external_job_id=job_id,
                posted_date=self.parse_date(raw.get("postedOn", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
