"""Zoox job scraper - Lever API (migrated from Greenhouse)."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import _lever_description
from typing import List, Optional
from datetime import datetime

@ScraperRegistry.register(category="custom")
class ZooxScraper(HTTPScraper):
    config = ScraperConfig(company_slug="zoox", company_name="Zoox", careers_url="https://zoox.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.lever.co/v0/postings/zoox"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL)
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")
        for job in data:
            if parsed := self.parse_job(job):
                all_jobs.append(parsed)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id", ""))
            categories = raw.get("categories", {})
            location = categories.get("location", "")
            department = categories.get("team", "")
            created_at = raw.get("createdAt", 0)
            posted_date = datetime.fromtimestamp(created_at / 1000) if created_at else None
            return ScrapedJob(
                title=raw.get("text", ""),
                location=location,
                job_url=raw.get("hostedUrl", f"https://jobs.lever.co/zoox/{job_id}"),
                external_job_id=job_id,
                job_description=_lever_description(raw),
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
