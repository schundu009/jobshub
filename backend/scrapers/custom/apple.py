"""Apple job scraper - Custom API."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class AppleScraper(HTTPScraper):
    """Scraper for Apple careers."""

    config = ScraperConfig(
        company_slug="apple",
        company_name="Apple",
        careers_url="https://jobs.apple.com",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://jobs.apple.com/api/role/search"

    CUSTOM_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://jobs.apple.com",
        "Referer": "https://jobs.apple.com/en-us/search",
        "X-Requested-With": "XMLHttpRequest",
    }

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        page = 0

        while True:
            params = {"page": page, "locale": "en-us", "sort": "newest"}
            data = await self.fetch_json(self.API_URL, params=params, headers=self.CUSTOM_HEADERS)

            if not data:
                break

            jobs = data.get("searchResults", [])
            if not jobs:
                break

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            total_pages = data.get("totalPages", 1)
            page += 1
            if page >= total_pages or page >= 20:
                break

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("postingTitle", "")
            job_id = str(raw.get("positionId", ""))
            locations = raw.get("locations", [])
            location = ", ".join([loc.get("name", "") for loc in locations]) if locations else ""
            posted_date_str = raw.get("postingDate", "")
            posted_date = None
            if posted_date_str:
                try:
                    posted_date = datetime.strptime(posted_date_str, "%Y-%m-%d")
                except:
                    pass
            job_url = f"https://jobs.apple.com/en-us/details/{job_id}"
            team = raw.get("team", {})
            department = team.get("teamName", "") if isinstance(team, dict) else ""

            return ScrapedJob(
                title=title, location=location, job_url=job_url, external_job_id=job_id,
                department=department, posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
