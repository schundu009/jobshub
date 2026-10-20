"""
Mastech Digital - jobs.mastech.com (own job board, JSON).

The board (CompanyId 16116) reads
GET https://jobs.mastech.com/job/GetJobs/<page>/<size>/null/16116/null/null/null/null/0/0/null
and the total from /job/GetJobCount/null/16116/...; postings carry city/state, pay
(SalaryLow/High + CompTypeDesc "Hourly"), employment type ("9+ Month Contract") and a
summary. Posting page: https://jobs.mastech.com/client/Job/<title-slug>-in-<City>-<ST>?jobNum=<n>&jc=<code>.
(Mastech's own corporate hiring is on SmartRecruiters "mastechdigital", a separate
board.) IT only. Verified 2026-10-20 (~47 postings).
"""

from urllib.parse import quote

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import parse_when
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, join_location, slugify
from ._own_site import OwnSiteStaffingScraper

BASE = "https://jobs.mastech.com"
TAIL = "null/16116/null/null/null/null/0/0/null"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class MastechScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="mastech",
        company_name="Mastech Digital",
        careers_url="https://jobs.mastech.com/",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Mastech Digital"
    PAGE_SIZE = 100
    IT_TITLE_KEYS = ("JobTitle",)

    def listing_items(self, payload):
        return self.expect_list(payload)

    async def fetch_raw(self) -> list:
        total = await self._http("GET", f"{BASE}/job/GetJobCount/{TAIL}")
        total = int(total) if str(total).isdigit() else None
        raw, page, seen = [], 1, 0
        while len(raw) < self.MAX_JOBS:
            jobs = self.listing_items(await self._http("GET", f"{BASE}/job/GetJobs/{page}/{self.PAGE_SIZE}/{TAIL}"))
            seen += len(jobs)
            raw.extend(self.take_it(jobs))
            if not jobs or len(jobs) < self.PAGE_SIZE or (total and seen >= total) or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        title = (raw.get("JobTitle") or "").strip()
        city, state = (raw.get("City") or "").strip(), (raw.get("State") or "").strip()
        url = (f"{BASE}/client/Job/{quote(slugify(title)[:50])}-in-{quote(city)}-{quote(state)}"
               f"?jobNum={raw.get('JobNum')}&jc={quote(str(raw.get('JobCode') or ''))}")
        remote = (raw.get("RemoteAvailable") or "").strip()
        location = join_location(city, state)
        if remote.lower() == "remote":
            location = f"{location} (Remote)" if location else "Remote"
        return self.make_job(
            title=title, location=location, job_url=url, external_job_id=raw.get("JobNum"),
            description=raw.get("JobDesc") or raw.get("JobDescriptionSummary") or raw.get("JobDescMini"),
            posted_date=parse_when(raw.get("DatePosted") or raw.get("EditDate")),
            employment_type_raw=raw.get("EmployTypeDesc"),
            pay_min=raw.get("SalaryLow"), pay_max=raw.get("SalaryHigh"), pay_period=raw.get("CompTypeDesc"),
            remote_type="remote" if remote.lower() == "remote" else None,
        )
