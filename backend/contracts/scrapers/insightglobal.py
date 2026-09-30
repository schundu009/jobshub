"""
Insight Global.

Endpoint: ``GET https://insightglobal.com/all/jobs?page=N&size=50&sort=postedDate,desc``
- the JSON the insightglobal.com/jobs Angular board loads (50 per page max).
Listings carry jobType ("Contract", "Contract, perm possible", "Perm") and a
structured pay rate. Descriptions live behind a per-job detail call and are not
fetched (one request per posting would blow the time budget).
Public posting URL: https://insightglobal.com/jobs/{requisitionId}.
Verified 2026-09-29 (~5,200 postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, is_us_state, join_location, parse_iso

API_URL = "https://insightglobal.com/all/jobs"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class InsightGlobalScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="insightglobal",
        company_name="Insight Global",
        careers_url="https://insightglobal.com/jobs/search/all/all",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Insight Global"
    PAGE_SIZE = 50

    async def fetch_raw(self) -> list:
        raw, page, pages = [], 1, None
        while len(raw) < self.MAX_JOBS:
            params = {
                "page": str(page), "size": str(self.PAGE_SIZE), "sort": "postedDate,desc",
                "filter.includeOnlyRemoteWork": "false", "filter.status": "active",
            }
            data = await self._http("GET", API_URL, params=params)
            jobs = self.expect_list(data, "jobs")
            raw.extend(jobs)
            pages = ((data.get("pageMetadata") or {}).get("totalPages")) or pages
            if not jobs or (pages and page >= pages) or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        addr = raw.get("workAddress") or {}
        state = addr.get("administrativeArea")
        country = addr.get("country") or addr.get("regionCode")
        if country and not is_us_country(country):
            return None
        # A remote posting anchored to a Canadian province is still a Canadian job.
        if not country and state and not is_us_state(state):
            return None
        pay = raw.get("payRate") or {}
        remote = bool(raw.get("workRemote"))
        location = join_location(addr.get("locality"), state) or ("Remote" if remote else "")
        req_id = raw.get("requisitionId")
        return self.make_job(
            title=raw.get("jobTitle"),
            location=location,
            job_url=f"https://insightglobal.com/jobs/{req_id}",
            external_job_id=req_id,
            posted_date=parse_iso(raw.get("postedDate")),
            employment_type_raw=raw.get("jobType"),
            pay_min=pay.get("min"),
            pay_max=pay.get("max"),
            pay_period=pay.get("type"),
            remote_type="remote" if remote else None,
        )
