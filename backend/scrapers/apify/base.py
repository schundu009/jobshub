"""
Base class for Apify-based scrapers.

Provides integration between Apify actors and the existing scraper system.
"""

import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from scrapers.base import BaseScraper, ScraperConfig, ScrapedJob, ScrapeResult, ScraperType
from services.apify_service import get_apify_service, ApifyService

logger = logging.getLogger(__name__)


@dataclass
class ApifyScraperConfig(ScraperConfig):
    """Configuration for Apify-based scrapers."""
    actor_key: str = ""  # Key from APIFY_ACTORS
    default_search_queries: list[str] = field(default_factory=lambda: ["software engineer"])
    default_location: str = "United States"
    max_items: int = 100
    timeout_secs: int = 300

    def __post_init__(self):
        # Apify scrapers are always HTTP type (API-based)
        self.scraper_type = ScraperType.HTTP


class ApifyScraper(BaseScraper):
    """
    Base class for scrapers using Apify platform.

    Subclasses should:
    1. Set `config` with ApifyScraperConfig
    2. Override `get_actor_input()` to customize actor parameters
    3. Optionally override `parse_job()` for custom parsing
    """

    config: ApifyScraperConfig

    def __init__(
        self,
        rate_limiter=None,
        browser_pool=None,
        apify_service: Optional[ApifyService] = None,
        **kwargs
    ):
        """
        Initialize Apify scraper.

        Args:
            rate_limiter: Rate limiter (not used for Apify but kept for compatibility)
            browser_pool: Browser pool (not used for Apify)
            apify_service: Optional ApifyService instance
        """
        super().__init__(rate_limiter=rate_limiter, browser_pool=browser_pool)
        self._apify_service = apify_service

    @property
    def apify_service(self) -> ApifyService:
        """Get Apify service."""
        if not self._apify_service:
            self._apify_service = get_apify_service()
        return self._apify_service

    def get_actor_input(self, **kwargs) -> dict:
        """
        Get input parameters for the Apify actor.

        Override this method to customize actor input.

        Args:
            **kwargs: Additional parameters (e.g., search queries, location)

        Returns:
            Dict of actor input parameters
        """
        return {
            "searchQueries": kwargs.get("search_queries", self.config.default_search_queries),
            "location": kwargs.get("location", self.config.default_location),
            "maxItems": kwargs.get("max_items", self.config.max_items),
        }

    async def scrape(self, **kwargs) -> ScrapeResult:
        """
        Run the Apify actor and return results.

        Args:
            **kwargs: Parameters to pass to get_actor_input()

        Returns:
            ScrapeResult with scraped jobs
        """
        start_time = datetime.utcnow()

        if not self.apify_service.is_configured:
            return ScrapeResult(
                success=False,
                error_message="Apify API token not configured",
                started_at=start_time,
                completed_at=datetime.utcnow(),
            )

        try:
            # Get actor input
            actor_input = self.get_actor_input(**kwargs)

            logger.info(
                f"Running Apify actor {self.config.actor_key} for {self.config.company_name}"
            )

            # Run the actor
            result = await self.apify_service.run_actor(
                actor_key=self.config.actor_key,
                input_override=actor_input,
                wait_for_finish=True,
                timeout_secs=self.config.timeout_secs,
            )

            if result.get("status") == "error":
                return ScrapeResult(
                    success=False,
                    error_message=result.get("error", "Unknown error"),
                    started_at=start_time,
                    completed_at=datetime.utcnow(),
                )

            # Parse jobs
            jobs = []
            raw_jobs = result.get("jobs", [])

            for raw_job in raw_jobs:
                try:
                    parsed = self.parse_job(raw_job)
                    if parsed:
                        jobs.append(parsed)
                except Exception as e:
                    logger.warning(f"Failed to parse job: {e}")
                    continue

            return ScrapeResult(
                success=True,
                jobs=jobs,
                jobs_found=len(jobs),
                started_at=start_time,
                completed_at=datetime.utcnow(),
                duration_seconds=result.get("duration_seconds", 0),
            )

        except Exception as e:
            logger.exception(f"Error in Apify scraper {self.config.company_slug}")
            return ScrapeResult(
                success=False,
                error_message=str(e),
                started_at=start_time,
                completed_at=datetime.utcnow(),
            )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """
        Parse a raw job from Apify into a ScrapedJob.

        Override this for custom parsing logic.

        Args:
            raw: Raw job data from Apify

        Returns:
            ScrapedJob or None if parsing fails
        """
        title = raw.get("title", "").strip()
        if not title:
            return None

        # Extract salary if available
        salary_min = None
        salary_max = None
        salary_text = raw.get("salary_text", "") or raw.get("salary", "")

        if salary_text:
            # Try to parse salary range
            import re
            numbers = re.findall(r'\$?([\d,]+)', salary_text)
            if numbers:
                try:
                    salary_min = int(numbers[0].replace(",", ""))
                    if len(numbers) > 1:
                        salary_max = int(numbers[1].replace(",", ""))
                except (ValueError, IndexError):
                    pass

        return ScrapedJob(
            title=title,
            location=raw.get("location", ""),
            job_url=raw.get("job_url", ""),
            external_job_id=str(raw.get("external_job_id", "")),
            job_description=raw.get("description", ""),
            department=raw.get("department", ""),
            posted_date=raw.get("posted_date"),
            salary_min=salary_min,
            salary_max=salary_max,
            employment_type=raw.get("employment_type", ""),
            remote_type=self._detect_remote_type(title, raw.get("location", "")),
            raw_data={"company_name": raw.get("company_name", "")},
        )

    def _detect_remote_type(self, title: str, location: str) -> Optional[str]:
        """Detect remote work type from title/location."""
        combined = f"{title} {location}".lower()

        if "remote" in combined:
            if "hybrid" in combined:
                return "hybrid"
            return "remote"
        elif "on-site" in combined or "onsite" in combined:
            return "onsite"

        return None
