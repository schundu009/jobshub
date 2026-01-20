"""HPE (Hewlett Packard Enterprise) job scraper."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="other")
class HPEScraper(HTTPScraper):
    """Scraper for HPE careers."""

    config = ScraperConfig(
        company_slug="hpe",
        company_name="HPE",
        careers_url="https://careers.hpe.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=50,
    )

    API_URL = "https://careers.hpe.com/api/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        page = 1

        while page <= self.config.max_pages:
            params = {
                "page": page,
                "limit": 20,
                "sortBy": "posted_date",
                "descending": "true"
            }

            data = await self.fetch_json(self.API_URL, params=params)
            if not data:
                break

            jobs = data.get("jobs", data) if isinstance(data, dict) else data
            if not jobs or not isinstance(jobs, list):
                break

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            if len(jobs) < 20:
                break
            page += 1

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", raw.get("jobTitle", ""))
            job_id = str(raw.get("id", raw.get("jobId", "")))
            location = raw.get("location", raw.get("locationText", ""))
            if isinstance(location, list):
                location = ", ".join(location)

            posted_str = raw.get("postedDate", raw.get("posted_date", ""))
            posted_date = None
            if posted_str:
                try:
                    posted_date = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                except:
                    pass

            job_url = raw.get("url", raw.get("applyUrl", f"https://careers.hpe.com/job/{job_id}"))

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                job_description=raw.get("description", ""),
                department=raw.get("department", raw.get("category", "")),
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
