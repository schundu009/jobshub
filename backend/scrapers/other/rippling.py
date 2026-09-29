"""
Rippling Jobs Scraper.

Uses Rippling's Greenhouse-based careers API.
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


# DISABLED: board dead as of 2026-09-29; Rippling uses its own ATS (ats.rippling.com) - no mixin
@ScraperRegistry.register(category="other")
class RipplingScraper(HTTPScraper):
    """Scraper for Rippling careers."""

    config = ScraperConfig(
        company_slug="rippling",
        company_name="Rippling",
        careers_url="https://www.rippling.com/careers",
        scraper_type=ScraperType.HTTP,
        enabled=False,
        disabled_reason="board dead as of 2026-09-29; Rippling uses its own ATS (ats.rippling.com) - no mixin",
        rate_limit=20,
        api_url="https://boards-api.greenhouse.io/v1/boards/rippling/jobs",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Rippling Greenhouse API."""
        all_jobs = []

        try:
            params = {"content": "true"}
            data = await self.fetch_json(self.config.api_url, params=params)

            jobs = data.get("jobs", [])
            for job_data in jobs:
                dept = job_data.get("departments", [{}])
                dept_name = dept[0].get("name", "") if dept else ""

                if "engineering" in dept_name.lower() or "product" in dept_name.lower():
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
