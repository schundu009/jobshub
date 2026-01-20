"""Notion job scraper - Greenhouse API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class NotionScraper(HTTPScraper):
    """Scraper for Notion careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="notion",
        company_name="Notion",
        careers_url="https://www.notion.so/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/notion/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        params = {"content": "true"}
        data = await self.fetch_json(self.API_URL, params=params)

        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        jobs = data.get("jobs", [])
        for job in jobs:
            parsed = self.parse_job(job)
            if parsed:
                all_jobs.append(parsed)

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = str(raw.get("id", ""))
            location_data = raw.get("location", {})
            location = location_data.get("name", "") if isinstance(location_data, dict) else str(location_data)
            updated_at = raw.get("updated_at", "")
            posted_date = None
            if updated_at:
                try:
                    posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                except:
                    pass
            job_url = raw.get("absolute_url", f"https://boards.greenhouse.io/notion/jobs/{job_id}")
            description = raw.get("content", "")
            departments = raw.get("departments", [])
            department = departments[0].get("name", "") if departments else ""

            return ScrapedJob(
                title=title, location=location, job_url=job_url, external_job_id=job_id,
                job_description=description, department=department, posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
