"""Kong job scraper - Greenhouse API."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime

@ScraperRegistry.register(category="custom")
class KongScraper(HTTPScraper):
    config = ScraperConfig(company_slug="kong", company_name="Kong", careers_url="https://konghq.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/konghq/jobs"
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL, params={"content": "true"})
        if not data: return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")
        for job in data.get("jobs", []):
            if parsed := self.parse_job(job): all_jobs.append(parsed)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)
    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id", ""))
            location_data = raw.get("location", {})
            location = location_data.get("name", "") if isinstance(location_data, dict) else str(location_data)
            updated_at = raw.get("updated_at", "")
            posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00")) if updated_at else None
            departments = raw.get("departments", [])
            return ScrapedJob(title=raw.get("title", ""), location=location, job_url=raw.get("absolute_url", ""), external_job_id=job_id, job_description=raw.get("content", ""), department=departments[0].get("name", "") if departments else "", posted_date=posted_date)
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
