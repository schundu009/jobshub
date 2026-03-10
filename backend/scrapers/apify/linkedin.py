"""
LinkedIn Jobs Scraper using Apify.

Uses Apify's LinkedIn Jobs scraper actors to fetch jobs without login.
"""

import logging
from typing import Optional

from scrapers.base import ScrapedJob, ScraperType
from scrapers.registry import ScraperRegistry
from .base import ApifyScraper, ApifyScraperConfig

logger = logging.getLogger(__name__)


@ScraperRegistry.register(category="apify")
class LinkedInJobsScraper(ApifyScraper):
    """
    LinkedIn Jobs scraper using Apify platform.

    Scrapes job listings from LinkedIn without requiring login.
    Uses bebity/linkedin-jobs-scraper actor.
    """

    config = ApifyScraperConfig(
        company_slug="linkedin-jobs",
        company_name="LinkedIn Jobs",
        careers_url="https://www.linkedin.com/jobs",
        scraper_type=ScraperType.HTTP,
        actor_key="linkedin_jobs",
        default_search_queries=[
            "software engineer",
            "data engineer",
            "machine learning engineer",
            "devops engineer",
            "cloud architect",
            "backend developer",
            "frontend developer",
            "full stack developer",
        ],
        default_location="United States",
        max_items=200,
        timeout_secs=600,
    )

    def get_actor_input(self, **kwargs) -> dict:
        """Get LinkedIn-specific actor input."""
        search_queries = kwargs.get("search_queries", self.config.default_search_queries)
        location = kwargs.get("location", self.config.default_location)
        max_items = kwargs.get("max_items", self.config.max_items)

        return {
            "searchQueries": search_queries if isinstance(search_queries, list) else [search_queries],
            "location": location,
            "maxItems": max_items,
            "proxy": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"]
            },
            "scrapeJobDetails": True,
        }

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse LinkedIn job data."""
        title = raw.get("title", "").strip()
        if not title:
            return None

        # Extract company name
        company_name = (
            raw.get("companyName") or
            raw.get("company_name") or
            raw.get("company") or
            "Unknown Company"
        )

        # Extract job URL
        job_url = (
            raw.get("jobUrl") or
            raw.get("job_url") or
            raw.get("link") or
            raw.get("url") or
            ""
        )

        # Extract job ID
        external_job_id = (
            raw.get("jobId") or
            raw.get("external_job_id") or
            raw.get("id") or
            ""
        )
        if not external_job_id and job_url:
            # Try to extract from URL
            import re
            match = re.search(r'/view/(\d+)', job_url)
            if match:
                external_job_id = match.group(1)

        # Parse salary
        salary_min = None
        salary_max = None
        salary_text = raw.get("salary") or raw.get("salary_text") or ""

        if salary_text:
            import re
            # Match patterns like "$100,000 - $150,000" or "$100K - $150K"
            numbers = re.findall(r'\$?([\d,]+)(?:K|k)?', salary_text)
            if numbers:
                try:
                    salary_min = int(numbers[0].replace(",", ""))
                    if "k" in salary_text.lower() and salary_min < 1000:
                        salary_min *= 1000
                    if len(numbers) > 1:
                        salary_max = int(numbers[1].replace(",", ""))
                        if "k" in salary_text.lower() and salary_max < 1000:
                            salary_max *= 1000
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
            department=raw.get("industries", "") or raw.get("department", ""),
            posted_date=raw.get("postedDate") or raw.get("publishedAt") or raw.get("posted_date"),
            salary_min=salary_min,
            salary_max=salary_max,
            employment_type=raw.get("employmentType") or raw.get("employment_type", ""),
            remote_type=remote_type,
            raw_data={"company_name": company_name},
        )


@ScraperRegistry.register(category="apify")
class LinkedInJobsAdvancedScraper(ApifyScraper):
    """
    Advanced LinkedIn Jobs scraper using curious_coder actor.

    Provides more detailed job data and better scaling.
    """

    config = ApifyScraperConfig(
        company_slug="linkedin-jobs-advanced",
        company_name="LinkedIn Jobs (Advanced)",
        careers_url="https://www.linkedin.com/jobs",
        scraper_type=ScraperType.HTTP,
        actor_key="linkedin_jobs_advanced",
        default_search_queries=[
            "software engineer",
            "data scientist",
            "product manager",
        ],
        default_location="United States",
        max_items=100,
        timeout_secs=600,
    )

    def get_actor_input(self, **kwargs) -> dict:
        """Get actor input for advanced LinkedIn scraper."""
        search_queries = kwargs.get("search_queries", self.config.default_search_queries)
        location = kwargs.get("location", self.config.default_location)
        max_items = kwargs.get("max_items", self.config.max_items)

        # This actor uses different input format
        return {
            "searchTerms": search_queries if isinstance(search_queries, list) else [search_queries],
            "location": location,
            "rows": max_items,
        }

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse job from advanced LinkedIn scraper."""
        title = raw.get("title", "").strip()
        if not title:
            return None

        company_name = raw.get("company") or raw.get("companyName") or "Unknown Company"

        return ScrapedJob(
            title=title,
            location=raw.get("location", ""),
            job_url=raw.get("url") or raw.get("jobUrl", ""),
            external_job_id=str(raw.get("jobId") or raw.get("id", "")),
            job_description=raw.get("description", ""),
            posted_date=raw.get("datePosted") or raw.get("postedAt"),
            employment_type=raw.get("type") or raw.get("employmentType", ""),
            raw_data={"company_name": company_name},
        )
