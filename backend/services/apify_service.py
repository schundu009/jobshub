"""
Apify Service for Cloud-Based Job Scraping.

Integrates with Apify platform to run actors for scraping jobs from:
- LinkedIn Jobs
- Indeed Jobs
- Glassdoor
- Other job boards

Benefits over local scrapers:
- Runs in the cloud, independent of local infrastructure
- Handles anti-bot measures automatically
- Proxy rotation built-in
- No Celery/worker dependency
"""

import logging
import os
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass

# Try to import apify_client, but don't fail if not installed
try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    ApifyClient = None
    APIFY_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ApifyActorConfig:
    """Configuration for an Apify actor."""
    actor_id: str
    name: str
    description: str
    default_input: dict
    job_parser: str  # Name of the parser function to use


# Popular Apify actors for job scraping
APIFY_ACTORS = {
    "linkedin_jobs": ApifyActorConfig(
        actor_id="bebity/linkedin-jobs-scraper",
        name="LinkedIn Jobs Scraper",
        description="Scrape job listings from LinkedIn without login",
        default_input={
            "searchQueries": ["software engineer"],
            "location": "United States",
            "maxItems": 100,
            "proxy": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"]
            }
        },
        job_parser="parse_linkedin_job"
    ),
    "linkedin_jobs_advanced": ApifyActorConfig(
        actor_id="curious_coder/linkedin-jobs-scraper",
        name="Advanced LinkedIn Jobs Scraper",
        description="Extract real-time job postings at scale",
        default_input={
            "searchTerms": ["software engineer"],
            "location": "United States",
            "rows": 100,
        },
        job_parser="parse_linkedin_job_advanced"
    ),
    "indeed_jobs": ApifyActorConfig(
        actor_id="misceres/indeed-scraper",
        name="Indeed Jobs Scraper",
        description="Scrape job listings from Indeed.com",
        default_input={
            "country": "US",
            "maxItems": 100,
            "position": "software engineer",
            "location": "United States",
        },
        job_parser="parse_indeed_job"
    ),
    "glassdoor_jobs": ApifyActorConfig(
        actor_id="bebity/glassdoor-scraper",
        name="Glassdoor Jobs Scraper",
        description="Scrape job listings from Glassdoor",
        default_input={
            "searchQueries": ["software engineer"],
            "location": "United States",
            "maxItems": 100,
        },
        job_parser="parse_glassdoor_job"
    ),
}


class ApifyService:
    """
    Service for interacting with Apify platform.

    Handles:
    - Running actors
    - Retrieving results
    - Parsing job data
    """

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize Apify service.

        Args:
            api_token: Apify API token. If not provided, uses APIFY_API_TOKEN env var.
        """
        self.api_token = api_token or os.environ.get("APIFY_API_TOKEN")
        self._client: Optional[ApifyClient] = None

    @property
    def client(self) -> ApifyClient:
        """Get or create Apify client."""
        if not APIFY_AVAILABLE:
            raise ValueError("apify-client package not installed. Run: pip install apify-client")
        if not self._client:
            if not self.api_token:
                raise ValueError("Apify API token not configured. Set APIFY_API_TOKEN environment variable.")
            self._client = ApifyClient(self.api_token)
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check if Apify is configured."""
        return APIFY_AVAILABLE and bool(self.api_token)

    def list_available_actors(self) -> list[dict]:
        """List available job scraping actors."""
        return [
            {
                "key": key,
                "actor_id": config.actor_id,
                "name": config.name,
                "description": config.description,
            }
            for key, config in APIFY_ACTORS.items()
        ]

    async def run_actor(
        self,
        actor_key: str,
        input_override: Optional[dict] = None,
        wait_for_finish: bool = True,
        timeout_secs: int = 300,
    ) -> dict:
        """
        Run an Apify actor and return results.

        Args:
            actor_key: Key from APIFY_ACTORS (e.g., "linkedin_jobs")
            input_override: Override default input parameters
            wait_for_finish: Whether to wait for the actor to finish
            timeout_secs: Maximum time to wait for completion

        Returns:
            Dict with status, jobs, and metadata
        """
        if actor_key not in APIFY_ACTORS:
            raise ValueError(f"Unknown actor: {actor_key}. Available: {list(APIFY_ACTORS.keys())}")

        config = APIFY_ACTORS[actor_key]

        # Merge input
        actor_input = {**config.default_input}
        if input_override:
            actor_input.update(input_override)

        logger.info(f"Running Apify actor: {config.actor_id} with input: {actor_input}")

        start_time = datetime.utcnow()

        try:
            # Run the actor
            actor_client = self.client.actor(config.actor_id)

            if wait_for_finish:
                run_result = actor_client.call(
                    run_input=actor_input,
                    timeout_secs=timeout_secs,
                )
            else:
                run_result = actor_client.start(run_input=actor_input)
                return {
                    "status": "started",
                    "run_id": run_result.get("id"),
                    "actor_key": actor_key,
                    "message": "Actor started. Use get_run_results to fetch results."
                }

            if not run_result:
                return {
                    "status": "failed",
                    "error": "Actor run returned no result",
                    "jobs": [],
                    "jobs_found": 0,
                }

            # Get results from dataset
            dataset_id = run_result.get("defaultDatasetId")
            if not dataset_id:
                return {
                    "status": "failed",
                    "error": "No dataset ID in result",
                    "jobs": [],
                    "jobs_found": 0,
                }

            dataset_client = self.client.dataset(dataset_id)
            items = dataset_client.list_items().items

            # Parse jobs
            parser = getattr(self, config.job_parser, self._default_parser)
            jobs = []
            for item in items:
                try:
                    job = parser(item)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    logger.warning(f"Failed to parse job: {e}")
                    continue

            duration = (datetime.utcnow() - start_time).total_seconds()

            return {
                "status": "success",
                "actor_key": actor_key,
                "run_id": run_result.get("id"),
                "jobs": jobs,
                "jobs_found": len(jobs),
                "raw_items": len(items),
                "duration_seconds": duration,
            }

        except Exception as e:
            logger.exception(f"Error running Apify actor {actor_key}")
            return {
                "status": "error",
                "error": str(e),
                "jobs": [],
                "jobs_found": 0,
            }

    async def get_run_results(self, run_id: str) -> dict:
        """
        Get results from a previous actor run.

        Args:
            run_id: The run ID returned from run_actor

        Returns:
            Dict with status and results
        """
        try:
            run_client = self.client.run(run_id)
            run_info = run_client.get()

            if run_info.get("status") != "SUCCEEDED":
                return {
                    "status": run_info.get("status", "UNKNOWN"),
                    "jobs": [],
                    "jobs_found": 0,
                }

            dataset_id = run_info.get("defaultDatasetId")
            if not dataset_id:
                return {
                    "status": "no_dataset",
                    "jobs": [],
                    "jobs_found": 0,
                }

            dataset_client = self.client.dataset(dataset_id)
            items = dataset_client.list_items().items

            return {
                "status": "success",
                "jobs": items,
                "jobs_found": len(items),
            }

        except Exception as e:
            logger.exception(f"Error getting run results: {run_id}")
            return {
                "status": "error",
                "error": str(e),
                "jobs": [],
                "jobs_found": 0,
            }

    # ============== Job Parsers ==============

    def parse_linkedin_job(self, raw: dict) -> Optional[dict]:
        """Parse LinkedIn job from bebity/linkedin-jobs-scraper."""
        if not raw.get("title"):
            return None

        return {
            "title": raw.get("title", "").strip(),
            "company_name": raw.get("companyName") or raw.get("company", ""),
            "location": raw.get("location", ""),
            "job_url": raw.get("jobUrl") or raw.get("link", ""),
            "external_job_id": raw.get("jobId") or raw.get("id", ""),
            "description": raw.get("description", ""),
            "posted_date": raw.get("postedDate") or raw.get("publishedAt"),
            "salary_text": raw.get("salary", ""),
            "employment_type": raw.get("employmentType", ""),
            "seniority_level": raw.get("seniorityLevel", ""),
            "source": "linkedin",
        }

    def parse_linkedin_job_advanced(self, raw: dict) -> Optional[dict]:
        """Parse LinkedIn job from curious_coder/linkedin-jobs-scraper."""
        if not raw.get("title"):
            return None

        return {
            "title": raw.get("title", "").strip(),
            "company_name": raw.get("company") or raw.get("companyName", ""),
            "location": raw.get("location", ""),
            "job_url": raw.get("url") or raw.get("jobUrl", ""),
            "external_job_id": raw.get("jobId") or str(raw.get("id", "")),
            "description": raw.get("description", ""),
            "posted_date": raw.get("datePosted") or raw.get("postedAt"),
            "salary_text": raw.get("salary", ""),
            "employment_type": raw.get("type") or raw.get("employmentType", ""),
            "source": "linkedin",
        }

    def parse_indeed_job(self, raw: dict) -> Optional[dict]:
        """Parse Indeed job from misceres/indeed-scraper."""
        if not raw.get("title") and not raw.get("positionName"):
            return None

        return {
            "title": (raw.get("positionName") or raw.get("title", "")).strip(),
            "company_name": raw.get("company", ""),
            "location": raw.get("location", ""),
            "job_url": raw.get("url") or raw.get("externalUrl", ""),
            "external_job_id": raw.get("id") or raw.get("jobKey", ""),
            "description": raw.get("description", ""),
            "posted_date": raw.get("postedAt") or raw.get("date"),
            "salary_text": raw.get("salary", ""),
            "employment_type": raw.get("jobType", ""),
            "source": "indeed",
        }

    def parse_glassdoor_job(self, raw: dict) -> Optional[dict]:
        """Parse Glassdoor job from bebity/glassdoor-scraper."""
        if not raw.get("title") and not raw.get("jobTitle"):
            return None

        return {
            "title": (raw.get("jobTitle") or raw.get("title", "")).strip(),
            "company_name": raw.get("employer") or raw.get("companyName", ""),
            "location": raw.get("location", ""),
            "job_url": raw.get("jobUrl") or raw.get("url", ""),
            "external_job_id": raw.get("jobId") or str(raw.get("id", "")),
            "description": raw.get("description", ""),
            "posted_date": raw.get("postedDate"),
            "salary_text": raw.get("salary") or raw.get("salaryRange", ""),
            "source": "glassdoor",
        }

    def _default_parser(self, raw: dict) -> Optional[dict]:
        """Default parser for unknown job formats."""
        title = raw.get("title") or raw.get("jobTitle") or raw.get("positionName")
        if not title:
            return None

        return {
            "title": str(title).strip(),
            "company_name": raw.get("company") or raw.get("companyName") or raw.get("employer", ""),
            "location": raw.get("location", ""),
            "job_url": raw.get("url") or raw.get("jobUrl") or raw.get("link", ""),
            "external_job_id": str(raw.get("id") or raw.get("jobId", "")),
            "description": raw.get("description", ""),
            "source": "apify",
        }


# Singleton instance
_apify_service: Optional[ApifyService] = None


def get_apify_service() -> ApifyService:
    """Get or create the Apify service singleton."""
    global _apify_service
    if _apify_service is None:
        _apify_service = ApifyService()
    return _apify_service
