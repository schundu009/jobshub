"""
Hugging Face Jobs Scraper.

Uses Workable's public job-board widget API (GET, no auth).
The previous v3 endpoint (/api/v3/accounts/{slug}/jobs) only accepts POST,
so the old GET silently returned nothing (fixed 2026-09-29).
"""

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
    """Scraper for Hugging Face careers (Workable)."""

    config = ScraperConfig(
        company_slug="huggingface",
        company_name="Hugging Face",
        careers_url="https://apply.workable.com/huggingface/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://apply.workable.com/api/v1/widget/accounts/huggingface",
    )

    async def scrape(self) -> ScrapeResult:
        data = await self.fetch_json(self.config.api_url)
        jobs = self.parse_all(self.expect_list(data, "jobs"))
        return ScrapeResult(success=True, jobs=jobs, pages_scraped=1)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            shortcode = raw.get("shortcode", "")
            if not (shortcode and raw.get("title")):
                return None
            location = ", ".join(
                p for p in (raw.get("city"), raw.get("state"), raw.get("country")) if p
            )
            if raw.get("telecommuting"):
                location = f"{location} (Remote)" if location else "Remote"
            return ScrapedJob(
                title=raw["title"],
                location=location,
                job_url=raw.get("url") or f"https://apply.workable.com/j/{shortcode}",
                external_job_id=shortcode,
                department=raw.get("department", ""),
                employment_type=raw.get("employment_type"),
                remote_type="remote" if raw.get("telecommuting") else None,
                posted_date=self.parse_date(raw.get("published_on", "")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
