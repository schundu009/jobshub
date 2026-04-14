"""Zoom job scraper - Workday API with job descriptions."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
import asyncio


@ScraperRegistry.register(category="custom")
class ZoomScraper(HTTPScraper):
    """Scraper for Zoom careers (Workday) - fetches full job descriptions."""

    config = ScraperConfig(
        company_slug="zoom",
        company_name="Zoom",
        careers_url="https://careers.zoom.us",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://zoom.wd5.myworkdayjobs.com/wday/cxs/zoom/Zoom/jobs"
    JOB_DETAIL_URL = "https://zoom.wd5.myworkdayjobs.com/wday/cxs/zoom/Zoom"

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

            # Process jobs in batches to avoid overwhelming the API
            for job in jobs:
                parsed = await self.parse_job_with_description(job)
                if parsed:
                    all_jobs.append(parsed)
                # Small delay between requests to be respectful
                await asyncio.sleep(0.1)

            if len(jobs) < limit:
                break
            offset += limit
            if offset >= 1000:
                break

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Required abstract method implementation — delegates to async version."""
        return None  # Not used directly; scrape() calls parse_job_with_description

    async def parse_job_with_description(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse job and fetch full description from job detail endpoint."""
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

            # Fetch job description from detail endpoint
            job_description = await self.fetch_job_description(external_path)

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                posted_date=posted_date,
                job_description=job_description,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None

    async def fetch_job_description(self, external_path: str) -> str:
        """Fetch full job description from Workday job detail API."""
        if not external_path:
            return ""

        try:
            # Workday job detail endpoint
            detail_url = f"{self.JOB_DETAIL_URL}{external_path}"
            data = await self.fetch_json(detail_url)

            if not data:
                return ""

            # Extract job description from the response
            job_posting = data.get("jobPostingInfo", {})

            # Try multiple possible description fields
            description = job_posting.get("jobDescription", "")
            if not description:
                description = job_posting.get("description", "")
            if not description:
                description = job_posting.get("additionalDetails", "")

            # Also try to get qualifications and responsibilities
            qualifications = job_posting.get("qualifications", "")
            responsibilities = job_posting.get("responsibilities", "")

            # Combine all content
            full_description = description
            if responsibilities:
                full_description += f"\n\nResponsibilities:\n{responsibilities}"
            if qualifications:
                full_description += f"\n\nQualifications:\n{qualifications}"

            return full_description.strip()

        except Exception as e:
            self.logger.debug(f"Could not fetch job description for {external_path}: {e}")
            return ""
