"""ContextualAI job scraper - uses Ashby API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="other")
class ContextualAIScraper(HTTPScraper):
    """Scraper for ContextualAI careers (Ashby)."""

    config = ScraperConfig(
        company_slug="contextualai",
        company_name="Contextual AI",
        careers_url="https://contextual.ai/careers/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/contextual"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        data = await self.fetch_json(self.API_URL)

        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        jobs = data.get("jobs", [])
        for job in jobs:
            parsed = self.parse_job(job)
            if parsed:
                all_jobs.append(parsed)

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = raw.get("id", "")

            location = raw.get("location", "")
            if isinstance(location, dict):
                location = location.get("name", "")

            published_at = raw.get("publishedAt", "")
            posted_date = None
            if published_at:
                try:
                    posted_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                except:
                    pass

            job_url = raw.get("jobUrl", f"https://jobs.ashbyhq.com/contextual/{job_id}")
            department = raw.get("department", "")
            if isinstance(department, dict):
                department = department.get("name", "")

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                job_description=raw.get("descriptionHtml", ""),
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
