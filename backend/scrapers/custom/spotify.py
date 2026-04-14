"""Spotify job scraper - Workday API (migrated from Greenhouse)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
import asyncio


@ScraperRegistry.register(category="custom")
class SpotifyScraper(HTTPScraper):
    """Scraper for Spotify careers (Workday API)."""

    config = ScraperConfig(
        company_slug="spotify",
        company_name="Spotify",
        careers_url="https://www.lifeatspotify.com/jobs",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=20,
    )

    # Spotify uses a custom Next.js site with no public API.
    # Jobs load client-side only — requires Playwright browser scraper.
    # Disabled until browser OOM issues are resolved on Railway.
    API_URL = "https://ghr.wd5.myworkdayjobs.com/wday/cxs/ghr/Spotify/jobs"
    _disabled = True

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

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            if len(jobs) < limit:
                break
            offset += limit
            if offset >= 2000:
                break
            await asyncio.sleep(0.2)

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            bullet = raw.get("bulletFields", [])
            job_id = bullet[0] if bullet else ""
            location = raw.get("locationsText", "")
            posted_on = raw.get("postedOn", "")
            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%d")
                except:
                    pass
            external_path = raw.get("externalPath", "")
            job_url = f"https://www.lifeatspotify.com/jobs{external_path}" if external_path else "https://www.lifeatspotify.com/jobs"

            return ScrapedJob(
                title=title, location=location, job_url=job_url, external_job_id=job_id,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Spotify job: {e}")
            return None
