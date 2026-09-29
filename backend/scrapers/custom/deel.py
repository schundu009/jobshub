"""Deel job scraper - Ashby API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


# DISABLED: board dead as of 2026-09-29; Ashby board empty, Deel hires via its own ATS (jobs.deel.com) - no mixin
@ScraperRegistry.register(category="custom")
class DeelScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="deel", company_name="Deel", careers_url="https://www.deel.com/careers",
        scraper_type=ScraperType.HTTP,
        enabled=False,
        disabled_reason="board dead as of 2026-09-29; Ashby board empty, Deel hires via its own ATS (jobs.deel.com) - no mixin", rate_limit=30, max_pages=10,
    )
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/deel"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL)
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")
        for job in data.get("jobs", []):
            parsed = self.parse_job(job)
            if parsed:
                all_jobs.append(parsed)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = str(raw.get("id", ""))
            location = raw.get("location", "Remote")
            published_at = raw.get("publishedAt", "")
            posted_date = datetime.fromisoformat(published_at.replace("Z", "+00:00")) if published_at else None
            job_url = raw.get("jobUrl", f"https://jobs.ashbyhq.com/deel/{job_id}")
            return ScrapedJob(title=title, location=location, job_url=job_url, external_job_id=job_id,
                department=raw.get("department", ""), posted_date=posted_date)
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
