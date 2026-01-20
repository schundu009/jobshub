"""Palo Alto Networks job scraper - uses Workday API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="other")
class PaloAltoNetworksScraper(HTTPScraper):
    """Scraper for Palo Alto Networks careers (Workday)."""

    config = ScraperConfig(
        company_slug="paloaltonetworks",
        company_name="Palo Alto Networks",
        careers_url="https://jobs.paloaltonetworks.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=50,
    )

    API_URL = "https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/External/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 20

        while offset < self.config.max_pages * limit:
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": ""
            }

            data = await self.fetch_json(self.API_URL, method="POST", payload=payload)
            if not data:
                break

            job_postings = data.get("jobPostings", [])
            if not job_postings:
                break

            for job in job_postings:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            external_id = raw.get("bulletFields", [""])[0] if raw.get("bulletFields") else ""
            location = raw.get("locationsText", "")
            posted_on = raw.get("postedOn", "")

            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%dT%H:%M:%S.%f%z")
                except:
                    try:
                        posted_date = datetime.strptime(posted_on.split("T")[0], "%Y-%m-%d")
                    except:
                        pass

            job_path = raw.get("externalPath", "")
            job_url = f"https://paloaltonetworks.wd5.myworkdayjobs.com/en-US/External{job_path}"

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=external_id or job_path,
                job_description="",
                department="",
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
