"""
Randstad USA (incl. Randstad Digital) - technology postings.

Endpoint: ``POST https://www.randstadusa.com/api/search/search-results`` - the call
the randstadusa.com/jobs/ search app makes, with the same route payload the
browser sends for /jobs/r-computer-and-mathematical-occupations/page-N/
(an allowed path; robots.txt disallows the /s-, /t-, /qt- filter routes, which
are not used). 30 postings per page, newest first. Postings carry type
("Contract", "Temp to Perm", "Temporary", "Permanent") and structured salary.
Verified 2026-09-29 (~700 postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_state, join_location, parse_iso

API_URL = "https://www.randstadusa.com/api/search/search-results"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class RandstadScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="randstad",
        company_name="Randstad",
        careers_url="https://www.randstadusa.com/jobs/r-computer-and-mathematical-occupations/",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Randstad"
    CATEGORY = "Computer and Mathematical Occupations"
    CATEGORY_SLUG = "r-computer-and-mathematical-occupations"
    PAGE_SIZE = 30
    IT_AMBIGUOUS_DEFAULT = True  # the listing is already the computer & mathematical category
    IT_CATEGORY_KEYS = ("categories",)

    def _payload(self, page: int) -> dict:
        route = self.CATEGORY_SLUG + (f"/page-{page}" if page > 1 else "")
        params = {"jobCategory": self.CATEGORY, "isInternal": False}
        if page > 1:
            params["page"] = str(page)
        return {"data": {
            "currentRoute": {"path": "/jobs/:searchParams*", "url": f"/jobs/{route}/",
                             "isExact": True, "params": {"searchParams": route}, "routeName": "search"},
            "currentLanguage": "en",
            "searchParams": params,
            "cookies": {},
        }}

    async def fetch_raw(self) -> list:
        raw, page, seen, listed = [], 1, set(), 0
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, json_body=self._payload(page))
            results = (data or {}).get("searchResults") if isinstance(data, dict) else None
            hits = self.expect_list(results or {}, "hits")
            fresh = [h for h in hits if h.get("id") not in seen]
            seen.update(h.get("id") for h in fresh)
            raw.extend(self.take_it(fresh))
            listed += len(fresh)
            total = (results or {}).get("totalSize") or 0
            if not fresh or listed >= total or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        loc = raw.get("jobLocation") or {}
        state = loc.get("stateAbbreviation") or loc.get("state")
        if state and not is_us_state(state):
            return None
        salary = raw.get("salary") or {}
        lo, hi = salary.get("min"), salary.get("max")
        if salary.get("fixed") and not lo:
            lo = salary.get("fixed")
        return self.make_job(
            title=raw.get("title"),
            location=join_location(loc.get("city"), state) or ("Remote" if raw.get("isRemote") else ""),
            job_url=raw.get("detailsUrl"),
            external_job_id=raw.get("atsReference") or raw.get("id"),
            description=raw.get("description") or raw.get("summary"),
            posted_date=parse_iso(raw.get("createdDate")),
            employment_type_raw=raw.get("type"),
            pay_min=lo, pay_max=hi, pay_period=salary.get("type"),
            department=(raw.get("categories") or [None])[0],
            remote_type="remote" if raw.get("isRemote") else None,
            extra={"business_line": raw.get("lobName")},
        )
