"""Intuitive Surgical job scraper - uses SmartRecruiters API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="other")
class IntuitiveSurgicalScraper(HTTPScraper):
    """Scraper for Intuitive Surgical careers (SmartRecruiters)."""

    config = ScraperConfig(
        company_slug="intuitivesurgical",
        company_name="Intuitive Surgical",
        careers_url="https://careers.intuitive.com/en/jobs/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=50,
    )

    API_URL = "https://api.smartrecruiters.com/v1/companies/Intuitive/postings"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 100

        while True:
            params = {"offset": offset, "limit": limit}
            data = await self.fetch_json(self.API_URL, params=params)

            if not data:
                break

            jobs = data.get("content", [])
            total = data.get("totalFound", 0)

            if not jobs:
                break

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            if len(jobs) < limit or offset + limit >= total:
                break
            offset += limit

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("name", "")
            job_id = raw.get("id", "") or raw.get("uuid", "")
            ref_number = raw.get("refNumber", "")

            # Location
            location_data = raw.get("location", {})
            city = location_data.get("city", "")
            region = location_data.get("region", "")
            country = location_data.get("country", "")

            location_parts = [p for p in [city, region] if p]
            location = ", ".join(location_parts) if location_parts else country

            # Remote/Hybrid info
            if location_data.get("remote"):
                location = f"{location} (Remote)" if location else "Remote"

            # Department
            department = ""
            if raw.get("department"):
                department = raw["department"].get("label", "")

            # Posted date
            released = raw.get("releasedDate", "")
            posted_date = None
            if released:
                try:
                    posted_date = datetime.fromisoformat(released.replace("Z", "+00:00"))
                except:
                    pass

            # Job URL - SmartRecruiters format
            job_url = f"https://jobs.smartrecruiters.com/Intuitive/{job_id}"

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=ref_number or job_id,
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
