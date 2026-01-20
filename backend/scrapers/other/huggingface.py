"""
Hugging Face Jobs Scraper.

Uses Hugging Face's Greenhouse-based careers API.
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


@ScraperRegistry.register(category="other")
class HuggingFaceScraper(HTTPScraper):
    """Scraper for Hugging Face careers."""

    config = ScraperConfig(
        company_slug="huggingface",
        company_name="Hugging Face",
        careers_url="https://apply.workable.com/huggingface/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://apply.workable.com/api/v3/accounts/huggingface/jobs",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Hugging Face careers API."""
        all_jobs = []

        try:
            data = await self.fetch_json(self.config.api_url)

            jobs = data.get("results", []) or data.get("jobs", [])
            for job_data in jobs:
                job = self.parse_job(job_data)
                if job:
                    all_jobs.append(job)

        except Exception as e:
            self.logger.error(f"Error fetching jobs: {e}")

        return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=1)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = raw.get("id", "") or raw.get("shortcode", "")

            location = raw.get("location", {})
            if isinstance(location, dict):
                loc_parts = [location.get("city", ""), location.get("country", "")]
                location_name = ", ".join(filter(None, loc_parts))
            else:
                location_name = str(location)

            return ScrapedJob(
                title=raw.get("title", ""),
                location=location_name,
                job_url=raw.get("url", "") or f"https://apply.workable.com/huggingface/j/{job_id}",
                external_job_id=str(job_id),
                department=raw.get("department", ""),
                posted_date=self.parse_date(raw.get("published_on", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
