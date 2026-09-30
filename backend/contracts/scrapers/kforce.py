"""
Kforce (Technology practice).

Endpoint: the Azure Cognitive Search index the kforce.com job search queries
straight from the browser:
``POST https://kforcewebeast.search.windows.net/indexes/kforcewebjobentity/docs/search``
with the public, query-only api-key embedded in kforce.com's app.min.js (it is
sent by every visitor's browser; it grants read access to the job index only).
Filtered to Industry 'Technology', newest first. TypeCode is "Contract" or
"Direct Hire"; SalaryMin/Max come with SalaryText "Hours" or "Years".
kforce.com's robots.txt disallows /svc and /kforcesvc, which this does not use.
Public posting URL: https://www.kforce.com/find-work/search-jobs/#/detail/{Id}.
Verified 2026-09-29 (~840 technology postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_state, join_location, parse_iso

API_URL = (
    "https://kforcewebeast.search.windows.net/indexes/kforcewebjobentity/docs/search"
    "?api-version=2016-09-01"
)
# Public query key from https://kforcewebeast.azureedge.net/scripts/dist/js/app.min.js
QUERY_KEY = "1603E4DC4C87A8E41D6BBDE4EEA4EFB7"
SELECT = ("Id, Title, Industry, PostDate, Responsibilities, Skills, City, State, Zip, "
          "SalaryMin, SalaryMax, SalaryText, ReferenceCode, TypeCode, Remote, VisaSponsorshipJob")


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class KforceScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="kforce",
        company_name="Kforce",
        careers_url="https://www.kforce.com/find-work/search-jobs/",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Kforce"
    PAGE_SIZE = 200
    INDUSTRY_FILTER = "Industry eq 'Technology'"

    async def fetch_raw(self) -> list:
        raw, skip = [], 0
        while len(raw) < self.MAX_JOBS:
            body = {
                "count": True, "select": SELECT, "filter": self.INDUSTRY_FILTER,
                "queryType": "simple", "search": "*", "orderby": "PostDate desc",
                "skip": skip, "top": self.PAGE_SIZE,
            }
            data = await self._http("POST", API_URL, json_body=body, headers={"api-key": QUERY_KEY})
            jobs = self.expect_list(data, "value")
            raw.extend(jobs)
            skip += len(jobs)
            total = data.get("@odata.count") or 0
            if not jobs or skip >= total or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        state = raw.get("State")
        if state and not is_us_state(state):
            return None
        period = {"hours": "hour", "years": "year"}.get((raw.get("SalaryText") or "").lower())
        description = "\n\n".join(p for p in (raw.get("Responsibilities"), raw.get("Skills")) if p)
        remote = (raw.get("Remote") or "").lower()
        return self.make_job(
            title=raw.get("Title"),
            location=join_location(raw.get("City"), state),
            job_url=f"https://www.kforce.com/find-work/search-jobs/#/detail/{raw.get('Id')}",
            external_job_id=raw.get("ReferenceCode") or raw.get("Id"),
            description=description,
            posted_date=parse_iso(raw.get("PostDate")),
            employment_type_raw=raw.get("TypeCode"),
            pay_min=raw.get("SalaryMin"),
            pay_max=raw.get("SalaryMax"),
            pay_period=period,
            department=raw.get("Industry"),
            remote_type={"full": "remote", "partial": "hybrid"}.get(remote),
        )
