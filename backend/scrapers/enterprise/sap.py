"""
SAP Jobs Scraper.

Uses SAP's careers API.
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
class SAPScraper(HTTPScraper):
    """Scraper for SAP careers."""

    config = ScraperConfig(
        company_slug="sap",
        company_name="SAP",
        careers_url="https://jobs.sap.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://jobs.sap.com/api/jobs",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape SAP careers API."""
        all_jobs = []
        page = 1

        while page <= self.config.max_pages:
            params = {
                "page": page,
                "limit": self.config.page_size,
                "department": "Engineering",
            }

            try:
                data = await self.fetch_json(self.config.api_url, params=params)

                jobs = data.get("jobs", [])
                if not jobs:
                    break

                for job_data in jobs:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

                total = data.get("totalCount", 0)
                if page * self.config.page_size >= total:
                    break

                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching page {page}: {e}")
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            pages_scraped=page,
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse SAP job data."""
        try:
            job_id = raw.get("id", "")

            return ScrapedJob(
                title=raw.get("title", ""),
                location=raw.get("location", ""),
                job_url=raw.get("url", "") or f"https://jobs.sap.com/job/{job_id}",
                external_job_id=str(job_id),
                job_description=raw.get("description", ""),
                department=raw.get("department", ""),
                posted_date=self.parse_date(raw.get("postedDate", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
