"""
Atlassian Jobs Scraper.

Uses Atlassian's careers API.
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
class AtlassianScraper(HTTPScraper):
    """Scraper for Atlassian careers."""

    config = ScraperConfig(
        company_slug="atlassian",
        company_name="Atlassian",
        careers_url="https://www.atlassian.com/company/careers/all-jobs",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://www.atlassian.com/endpoint/careers/listings",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Atlassian careers API."""
        all_jobs = []

        try:
            # Atlassian's API returns all jobs at once
            data = await self.fetch_json(self.config.api_url)

            jobs = data.get("jobs", []) or data.get("listings", []) or data
            if isinstance(jobs, list):
                for job_data in jobs:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

        except Exception as e:
            self.logger.error(f"Error fetching jobs: {e}")

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            pages_scraped=1,
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse Atlassian job data."""
        try:
            job_id = raw.get("id", "") or raw.get("jobId", "")

            # Get location
            locations = raw.get("locations", [])
            location = ", ".join(locations) if isinstance(locations, list) else raw.get("location", "")

            return ScrapedJob(
                title=raw.get("title", "") or raw.get("name", ""),
                location=location,
                job_url=raw.get("url", "") or raw.get("applyUrl", ""),
                external_job_id=str(job_id),
                job_description=raw.get("description", ""),
                department=raw.get("team", "") or raw.get("department", ""),
                posted_date=self.parse_date(raw.get("postedDate", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
