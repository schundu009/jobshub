"""Apple job scraper - server-rendered search page (jobs.apple.com)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult, UnexpectedResponseError
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
import asyncio
import json
import re


@ScraperRegistry.register(category="custom")
class AppleScraper(HTTPScraper):
    """Scraper for Apple careers."""

    config = ScraperConfig(
        company_slug="apple",
        company_name="Apple",
        careers_url="https://jobs.apple.com",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    # The old JSON API (/api/role/search) now redirects to apple.com/pagenotfound.
    # The search page server-renders its results into
    # window.__staticRouterHydrationData (20 per page, sorted newest first).
    SEARCH_URL = "https://jobs.apple.com/en-us/search"
    MAX_PAGES = 40  # newest 800 of ~6k roles; ~1s/page keeps us under the 120s soft limit
    _HYDRATION_RE = re.compile(
        r"window\.__staticRouterHydrationData\s*=\s*JSON\.parse\((\".*?\")\);", re.S
    )

    def _extract_search(self, html: str) -> dict:
        m = self._HYDRATION_RE.search(html)
        if not m:
            raise UnexpectedResponseError("Apple search page has no hydration data")
        data = json.loads(json.loads(m.group(1)))
        search = (data.get("loaderData") or {}).get("search")
        if not isinstance(search, dict):
            raise UnexpectedResponseError("Apple hydration data has no 'search' loader")
        return search

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        page = 1
        while page <= self.MAX_PAGES:
            html = await self.fetch_html(self.SEARCH_URL, params={"sort": "newest", "page": page})
            search = self._extract_search(html)
            jobs = self.expect_list(search, "searchResults")
            if not jobs:
                break
            all_jobs.extend(self.parse_all(jobs))
            total = search.get("totalRecords") or 0
            if page * len(jobs) >= total:
                break
            page += 1
            await asyncio.sleep(0.2)

        # Paging a newest-first list can repeat rows as new postings land, and
        # one requisition can appear more than once; keep the first of each id.
        seen = set()
        all_jobs = [j for j in all_jobs if not (j.external_job_id in seen or seen.add(j.external_job_id))]
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), pages_scraped=page)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("postingTitle", "")
            job_id = str(raw.get("positionId", ""))
            locations = raw.get("locations", [])
            location = ", ".join([loc.get("name", "") for loc in locations]) if locations else ""
            if not job_id:
                return None
            gmt = raw.get("postDateInGMT") or ""
            posted_date = self.parse_date(raw.get("postingDate", ""))
            if gmt:
                try:
                    posted_date = datetime.strptime(gmt[:19], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    pass
            slug = raw.get("transformedPostingTitle") or ""
            job_url = f"https://jobs.apple.com/en-us/details/{job_id}" + (f"/{slug}" if slug else "")
            team = raw.get("team", {})
            department = team.get("teamName", "") if isinstance(team, dict) else ""

            return ScrapedJob(
                title=title, location=location, job_url=job_url, external_job_id=job_id,
                job_description=raw.get("jobSummary") or None,
                department=department, posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
