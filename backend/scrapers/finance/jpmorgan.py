"""
JPMorgan Chase Jobs Scraper.

Uses JPMorgan's careers API.
"""

from datetime import datetime
from typing import Optional

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="finance")
class JPMorganScraper(HTTPScraper):
    """Scraper for JPMorgan Chase careers."""

    config = ScraperConfig(
        company_slug="jpmorgan",
        company_name="JPMorgan Chase",
        careers_url="https://careers.jpmorgan.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://careers.jpmorgan.com/api/v2/jobs",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape JPMorgan careers API."""
        all_jobs = []
        page = 1

        while page <= self.config.max_pages:
            params = {
                "page": page,
                "limit": self.config.page_size,
                "category": "Technology",
            }

            try:
                data = await self.fetch_json(self.config.api_url, params=params)

                jobs = data.get("jobs", []) or data.get("results", [])
                if not jobs:
                    break

                for job_data in jobs:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

                total = data.get("totalCount", 0) or data.get("total", 0)
                if page * self.config.page_size >= total:
                    break

                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching page {page}: {e}")
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            pages_scraped=page,
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse JPMorgan job data."""
        try:
            job_id = raw.get("id", "") or raw.get("requisitionId", "")

            return ScrapedJob(
                title=raw.get("title", ""),
                location=raw.get("location", "") or raw.get("city", ""),
                job_url=raw.get("url", "") or f"https://careers.jpmorgan.com/job/{job_id}",
                external_job_id=str(job_id),
                job_description=raw.get("description", ""),
                department=raw.get("category", "") or raw.get("businessUnit", ""),
                posted_date=self.parse_date(raw.get("postedDate", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
