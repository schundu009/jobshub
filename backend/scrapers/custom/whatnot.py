"""Whatnot job scraper - Ashby (hosted board "whatnot", via Ashby's job-board GraphQL)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import Dict, List, Optional


# Moved to Ashby (verified 2026-09-29). Whatnot has the public posting-api disabled
# (api.ashbyhq.com/posting-api/job-board/whatnot -> 404), but its hosted board
# jobs.ashbyhq.com/whatnot is live and served by Ashby's non-user GraphQL endpoint.
@ScraperRegistry.register(category="custom")
class WhatnotScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="whatnot", company_name="Whatnot", careers_url="https://www.whatnot.com/careers/discover",
        scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10,
    )
    API_URL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    BOARD = "whatnot"
    QUERY = (
        "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {"
        " jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {"
        " teams { id name parentTeamId }"
        " jobPostings { id title teamId locationName workplaceType employmentType"
        " secondaryLocations { locationName } } } }"
    )

    async def scrape(self) -> ScrapeResult:
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": self.BOARD},
            "query": self.QUERY,
        }
        data = await self.fetch_json(self.API_URL, method="POST", json_data=payload)
        board = ((data or {}).get("data") or {}).get("jobBoard")
        if not board:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No job board data")
        self._teams: Dict[str, str] = {t["id"]: t.get("name", "") for t in board.get("teams") or []}
        all_jobs: List[ScrapedJob] = self.parse_all(board.get("jobPostings") or [])
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id", ""))
            locations = [raw.get("locationName")] + [
                s.get("locationName") for s in raw.get("secondaryLocations") or []
            ]
            workplace = (raw.get("workplaceType") or "").lower()
            return ScrapedJob(
                title=raw.get("title", ""),
                location="; ".join(l for l in locations if l) or "Remote",
                job_url=f"https://jobs.ashbyhq.com/{self.BOARD}/{job_id}",
                external_job_id=job_id,
                department=getattr(self, "_teams", {}).get(raw.get("teamId"), ""),
                employment_type=raw.get("employmentType"),
                remote_type=workplace if workplace in ("remote", "hybrid") else ("on-site" if workplace == "onsite" else None),
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
