"""Zoom job scraper - Workday API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class ZoomScraper(HTTPScraper):
    """Scraper for Zoom careers (Workday)."""

    config = ScraperConfig(
        company_slug="zoom",
        company_name="Zoom",
        careers_url="https://careers.zoom.us",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://zoom.wd5.myworkdayjobs.com/wday/cxs/zoom/Zoom/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 50

        while True:
            payload = {"limit": limit, "offset": offset, "searchText": ""}
            data = await self.fetch_json(self.API_URL, method="POST", json=payload)

            if not data:
                break

            jobs = data.get("jobPostings", [])
            if not jobs:
                break

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            if len(jobs) < limit:
                break
            offset += limit
            if offset >= 1000:
                break

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = raw.get("bulletFields", [""])[0] if raw.get("bulletFields") else ""
            location = raw.get("locationsText", "")
            posted_on = raw.get("postedOn", "")
            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%d")
                except:
                    pass
            external_path = raw.get("externalPath", "")
            job_url = f"https://zoom.wd5.myworkdayjobs.com/Zoom{external_path}"

            return ScrapedJob(
                title=title, location=location, job_url=job_url, external_job_id=job_id,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
