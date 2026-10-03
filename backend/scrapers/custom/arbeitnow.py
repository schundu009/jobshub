"""Arbeitnow job scraper — free public API, no auth required.

Provides tech jobs globally, paginated.
API: https://www.arbeitnow.com/api/job-board-api
"""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime

from services.job_location import job_countries


@ScraperRegistry.register(category="custom")
class ArbeitnowScraper(HTTPScraper):
    """Scraper for Arbeitnow — free API, paginated tech jobs."""

    config = ScraperConfig(
        company_slug="arbeitnow",
        company_name="Arbeitnow",
        careers_url="https://www.arbeitnow.com",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://www.arbeitnow.com/api/job-board-api"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        seen_slugs = set()
        page = 1

        while page <= self.config.max_pages:
            params = {"page": page}
            try:
                data = await self.fetch_json(self.API_URL, params=params)
            except Exception:
                break

            if not data:
                break

            jobs = data.get("data", [])
            if not jobs:
                break

            for job in jobs:
                slug = job.get("slug", "")
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            # Check pagination
            links = data.get("links", {})
            if not links.get("next"):
                break
            page += 1

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "").strip()
            if not title:
                return None

            company = raw.get("company_name", "")
            location = raw.get("location", "")
            remote = raw.get("remote", False)
            # A German board: its locations are bare cities ("Bonn"). Name the
            # country unless the location already does, so country filters work.
            if not job_countries(location):
                location = f"{location}, Germany" if location else ("Remote, Germany" if remote else "Germany")

            created = raw.get("created_at", 0)
            posted_date = datetime.fromtimestamp(created) if created else None

            tags = raw.get("tags", [])
            department = tags[0] if tags else ""
            description = raw.get("description", "")

            return ScrapedJob(
                title=title,
                location=location,
                job_url=raw.get("url", ""),
                external_job_id=raw.get("slug", ""),
                job_description=description,
                department=department,
                posted_date=posted_date,
                raw_data={"company_name": company},
            )
        except Exception as e:
            self.logger.error(f"Error parsing Arbeitnow job: {e}")
            return None
