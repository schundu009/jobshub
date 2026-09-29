"""
Atlassian Jobs Scraper.

Uses Atlassian's careers API.
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


@ScraperRegistry.register(category="enterprise")
class AtlassianScraper(HTTPScraper):
    """Scraper for Atlassian careers."""

    config = ScraperConfig(
        company_slug="atlassian",
        company_name="Atlassian",
        careers_url="https://www.atlassian.com/company/careers/all-jobs",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://www.atlassian.com/endpoint/careers/listings",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Atlassian careers listings (one request returns every opening)."""
        # The endpoint returns a bare JSON list; the old code called .get() on it,
        # raised inside a broad except and reported 0 jobs as success.
        data = await self.fetch_json(self.config.api_url)
        jobs = self.expect_list(data)
        return ScrapeResult(success=True, jobs=self.parse_all(jobs), pages_scraped=1)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse an Atlassian listing (backed by iCIMS portals)."""
        try:
            job_id = raw.get("id")
            title = raw.get("title")
            if not job_id or not title:
                return None
            portal = raw.get("portalJobPost") or {}
            locations = raw.get("locations") or []
            description = "".join(
                raw.get(k) or "" for k in ("overview", "responsibilities", "qualifications")
            )
            return ScrapedJob(
                title=title,
                location="; ".join(locations) if isinstance(locations, list) else str(locations),
                job_url=portal.get("portalUrl")
                or f"https://www.atlassian.com/company/careers/details/{job_id}",
                external_job_id=str(job_id),
                job_description=description or None,
                department=raw.get("category", ""),
                employment_type=raw.get("type"),
                posted_date=self.parse_date((portal.get("updatedDate") or "")[:10]),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
