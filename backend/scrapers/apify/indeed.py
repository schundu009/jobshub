"""
Indeed Jobs Scraper using Apify.

Uses Apify's Indeed scraper actor to fetch jobs.
"""

import logging
from typing import Optional

from scrapers.base import ScrapedJob, ScraperType
from scrapers.registry import ScraperRegistry
from .base import ApifyScraper, ApifyScraperConfig

logger = logging.getLogger(__name__)


@ScraperRegistry.register(category="apify")
class IndeedJobsScraper(ApifyScraper):
    """
    Indeed Jobs scraper using Apify platform.

    Scrapes job listings from Indeed.com.
    """

    config = ApifyScraperConfig(
        company_slug="indeed-jobs",
        company_name="Indeed Jobs",
        careers_url="https://www.indeed.com",
        scraper_type=ScraperType.HTTP,
        actor_key="indeed_jobs",
        default_search_queries=[
            "software engineer",
            "data engineer",
            "devops engineer",
        ],
        default_location="United States",
        max_items=200,
        timeout_secs=600,
    )

    def get_actor_input(self, **kwargs) -> dict:
        """Get Indeed-specific actor input."""
        search_queries = kwargs.get("search_queries", self.config.default_search_queries)
        location = kwargs.get("location", self.config.default_location)
        max_items = kwargs.get("max_items", self.config.max_items)

        # Indeed scraper uses different field names
        position = search_queries[0] if isinstance(search_queries, list) else search_queries

        return {
            "country": "US",
            "position": position,
            "location": location,
            "maxItems": max_items,
        }

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse Indeed job data."""
        title = (raw.get("positionName") or raw.get("title", "")).strip()
        if not title:
            return None

        company_name = raw.get("company", "Unknown Company")

        # Extract job URL
        job_url = (
            raw.get("url") or
            raw.get("externalUrl") or
            raw.get("jobUrl") or
            ""
        )

        # Extract job ID
        external_job_id = (
            raw.get("id") or
            raw.get("jobKey") or
            raw.get("externalJobId") or
            ""
        )

        # Parse salary
        salary_min = None
        salary_max = None
        salary_text = raw.get("salary", "")

        if salary_text:
            import re
            numbers = re.findall(r'\$?([\d,]+)', salary_text)
            if numbers:
                try:
                    salary_min = int(numbers[0].replace(",", ""))
                    if len(numbers) > 1:
                        salary_max = int(numbers[1].replace(",", ""))
                except (ValueError, IndexError):
                    pass

        # Detect remote type
        location = raw.get("location", "")
        remote_type = None
        combined = f"{title} {location}".lower()

        if "remote" in combined:
            remote_type = "hybrid" if "hybrid" in combined else "remote"
        elif "on-site" in combined or "onsite" in combined:
            remote_type = "onsite"

        return ScrapedJob(
            title=title,
            location=location,
            job_url=job_url,
            external_job_id=str(external_job_id),
            job_description=raw.get("description", ""),
            posted_date=raw.get("postedAt") or raw.get("date"),
            salary_min=salary_min,
            salary_max=salary_max,
            employment_type=raw.get("jobType", ""),
            remote_type=remote_type,
            raw_data={"company_name": company_name},
        )


# GlassdoorJobsScraper removed — bebity/glassdoor-scraper was pulled from Apify marketplace.
# actor_key="glassdoor_jobs" no longer exists in APIFY_ACTORS, causing "Unknown actor" errors.
