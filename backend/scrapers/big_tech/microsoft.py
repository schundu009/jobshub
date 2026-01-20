"""
Microsoft Jobs Scraper.

Uses Microsoft's careers API at careers.microsoft.com.
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
class MicrosoftScraper(HTTPScraper):
    """Scraper for Microsoft careers."""

    config = ScraperConfig(
        company_slug="microsoft",
        company_name="Microsoft",
        careers_url="https://careers.microsoft.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://gcsservices.careers.microsoft.com/search/api/v1/search",
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Microsoft careers API."""
        all_jobs = []
        page = 1
        total_pages = None

        while page <= self.config.max_pages:
            payload = {
                "posted": "past-week",
                "pg": page,
                "pgSz": self.config.page_size,
                "o": "Recent",
                "flt": True,
            }

            try:
                data = await self.fetch_json(
                    self.config.api_url,
                    method="POST",
                    json_data=payload,
                )

                result = data.get("operationResult", {}).get("result", {})
                jobs = result.get("jobs", [])

                if not jobs:
                    break

                for job_data in jobs:
                    job = self.parse_job(job_data)
                    if job:
                        all_jobs.append(job)

                # Get total pages on first request
                if total_pages is None:
                    total_count = result.get("totalJobs", 0)
                    total_pages = (total_count // self.config.page_size) + 1

                if page >= total_pages:
                    break

                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching page {page}: {e}")
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            pages_scraped=page,
            total_pages=total_pages,
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse Microsoft job data."""
        try:
            job_id = raw.get("jobId", "")
            properties = raw.get("properties", {})

            # Extract locations
            locations = properties.get("locations", [])
            location = ", ".join(locations) if locations else properties.get("primaryLocation", "")

            # Parse posted date
            posted_str = properties.get("datePosted", "")
            posted_date = self.parse_date(posted_str)

            return ScrapedJob(
                title=raw.get("title", ""),
                location=location,
                job_url=f"https://careers.microsoft.com/us/en/job/{job_id}",
                external_job_id=job_id,
                job_description=properties.get("description", ""),
                department=properties.get("discipline", ""),
                posted_date=posted_date,
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
