"""
Amazon Jobs Scraper.

Uses Amazon's jobs API at amazon.jobs.
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


@ScraperRegistry.register(category="big_tech")
class AmazonScraper(HTTPScraper):
    """Scraper for Amazon careers."""

    config = ScraperConfig(
        company_slug="amazon",
        company_name="Amazon",
        careers_url="https://www.amazon.jobs/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://www.amazon.jobs/en/search.json",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Amazon jobs API."""
        all_jobs = []
        offset = 0
        page = 0

        while page < self.config.max_pages:
            params = {
                "offset": offset,
                "result_limit": self.config.page_size,
                "sort": "recent",
                "category[]": "software-development",
            }

            try:
                data = await self.fetch_json(
                    self.config.api_url,
                    params=params,
                )

                jobs = data.get("jobs", [])

                if not jobs:
                    break

                for job_data in jobs:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

                # Check if more pages
                hits = data.get("hits", 0)
                if offset + len(jobs) >= hits:
                    break

                offset += self.config.page_size
                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching offset {offset}: {e}")
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            pages_scraped=page + 1,
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse Amazon job data."""
        try:
            job_id = raw.get("id_icims", "") or raw.get("id", "")

            # Build location string
            location_parts = []
            if raw.get("city"):
                location_parts.append(raw["city"])
            if raw.get("state"):
                location_parts.append(raw["state"])
            if raw.get("country_code"):
                location_parts.append(raw["country_code"])
            location = ", ".join(location_parts)

            # Parse posted date
            posted_str = raw.get("posted_date", "")
            posted_date = self.parse_date(posted_str)

            # Build job URL
            job_path = raw.get("job_path", "")
            job_url = f"https://www.amazon.jobs{job_path}" if job_path else ""

            return ScrapedJob(
                title=raw.get("title", ""),
                location=location,
                job_url=job_url,
                external_job_id=str(job_id),
                job_description=raw.get("description", "") or raw.get("basic_qualifications", ""),
                department=raw.get("job_category", ""),
                posted_date=posted_date,
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
