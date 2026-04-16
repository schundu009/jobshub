"""RemoteOK job scraper — free public API, no auth required.

Provides remote-first jobs across all tech roles.
API: https://remoteok.com/api
Rate limit: be polite, 1 req/sec.
"""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class RemoteOKScraper(HTTPScraper):
    """Scraper for RemoteOK — free API, ~100 remote tech jobs."""

    config = ScraperConfig(
        company_slug="remoteok",
        company_name="RemoteOK",
        careers_url="https://remoteok.com",
        scraper_type=ScraperType.HTTP,
        rate_limit=60,  # Be polite
        max_pages=1,
    )

    API_URL = "https://remoteok.com/api"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        headers = {"User-Agent": "Camora/1.0 (job aggregator)"}
        data = await self.fetch_json(self.API_URL, headers=headers)

        if not data or not isinstance(data, list):
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        for item in data:
            # First item is legal notice, skip non-job items
            if not isinstance(item, dict) or not item.get("position"):
                continue
            parsed = self.parse_job(item)
            if parsed:
                all_jobs.append(parsed)

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("position", "").strip()
            if not title:
                return None
            company = raw.get("company", "")
            location = raw.get("location", "Remote")
            if not location or location.strip() == "":
                location = "Remote"
            tags = raw.get("tags", [])
            department = tags[0] if tags else ""
            date_str = raw.get("date", "")
            posted_date = None
            if date_str:
                try:
                    posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            salary_min = raw.get("salary_min")
            salary_max = raw.get("salary_max")
            description = raw.get("description", "")

            return ScrapedJob(
                title=title,
                location=location,
                job_url=raw.get("url", ""),
                external_job_id=str(raw.get("id", "")),
                job_description=description,
                department=department,
                posted_date=posted_date,
                salary_min=int(salary_min) if salary_min else None,
                salary_max=int(salary_max) if salary_max else None,
                raw_data={"company_name": company},
            )
        except Exception as e:
            self.logger.error(f"Error parsing RemoteOK job: {e}")
            return None
