"""
CoreWeave Jobs Scraper.

Uses CoreWeave's Greenhouse-based careers API.
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


@ScraperRegistry.register(category="other")
class CoreWeaveScraper(HTTPScraper):
    """Scraper for CoreWeave careers."""

    config = ScraperConfig(
        company_slug="coreweave",
        company_name="CoreWeave",
        careers_url="https://coreweave.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://boards-api.greenhouse.io/v1/boards/coreweave/jobs",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape CoreWeave Greenhouse API."""
        all_jobs = []

        try:
            params = {"content": "true"}
            data = await self.fetch_json(self.config.api_url, params=params)

            jobs = data.get("jobs", [])
            for job_data in jobs:
                job = self.parse_job(job_data)
                if job:
                    all_jobs.append(job)

        except Exception as e:
            self.logger.error(f"Error fetching jobs: {e}")

        return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=1)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = raw.get("id", "")
            location = raw.get("location", {})
            location_name = location.get("name", "") if isinstance(location, dict) else str(location)
            depts = raw.get("departments", [])
            department = depts[0].get("name", "") if depts else ""

            return ScrapedJob(
                title=raw.get("title", ""),
                location=location_name,
                job_url=raw.get("absolute_url", ""),
                external_job_id=str(job_id),
                job_description=self.clean_html(raw.get("content", "")),
                department=department,
                posted_date=self.parse_date(raw.get("updated_at", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
