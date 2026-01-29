"""You.com job scraper - uses Lever API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="other")
class YouComScraper(HTTPScraper):
    """Scraper for You.com careers (Lever)."""

    config = ScraperConfig(
        company_slug="youcom",
        company_name="You.com",
        careers_url="https://you.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.lever.co/v0/postings/you"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        data = await self.fetch_json(self.API_URL)

        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        if isinstance(data, list):
            for job in data:
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
            title = raw.get("text", "")
            job_id = raw.get("id", "")

            categories = raw.get("categories", {})
            location = categories.get("location", "")
            department = categories.get("team", "")

            created_at = raw.get("createdAt", 0)
            posted_date = None
            if created_at:
                try:
                    posted_date = datetime.fromtimestamp(created_at / 1000)
                except:
                    pass

            job_url = raw.get("hostedUrl", f"https://jobs.lever.co/you/{job_id}")
            description = raw.get("descriptionPlain", "")

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                job_description=description,
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
