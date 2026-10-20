"""
Manpower (ManpowerGroup US) - www.manpower.com/en-us/search (own Sitecore jobs API).

The search page posts {"filter": {"offset": <page index>, "limit": n, "language": "en", ...}}
to https://www.manpower.com/api/services/Jobs/searchjobs (jobsItems with title,
location, type, publish date and the full description; ~2,800 US postings, mostly
light industrial). Posting page: https://www.manpower.com/en-us<jobURL minus /en>.
Manpower's IT staffing is Experis (its own scraper); IT only keeps the few tech roles.
Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, parse_iso
from ._own_site import OwnSiteStaffingScraper

API_URL = "https://www.manpower.com/api/services/Jobs/searchjobs"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class ManpowerScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="manpower",
        company_name="Manpower",
        careers_url="https://www.manpower.com/en-us/search",
        scraper_type=ScraperType.HTTP,
        request_timeout=45,
    )
    AGENCY_NAME = "Manpower"
    PAGE = 500
    MAX_PAGES = 10
    IT_TITLE_KEYS = ("jobTitle",)
    IT_CATEGORY_KEYS = ("domain",)

    def listing_items(self, payload):
        return self.expect_list(payload, "jobsItems")

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(self.MAX_PAGES):
            body = {"filter": {"offset": page, "totalCount": 0, "limit": self.PAGE, "searchkeyword": None,
                               "haslocation": False, "language": "en"}}
            jobs = [j for j in self.listing_items(await self._http("POST", API_URL, json_body=body,
                                                                    headers={"Referer": "https://www.manpower.com/en-us/search"}))
                    if j.get("jobID") not in seen]
            if not jobs:
                break
            seen.update(j.get("jobID") for j in jobs)
            raw.extend(self.take_it(j for j in jobs if not j.get("isExpired")))
            if self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        path = raw.get("jobURL") or ""
        if path.startswith("/en/"):
            path = "/en-us/" + path[4:]
        return self.make_job(
            title=raw.get("jobTitle"), location=raw.get("jobLocation"),
            job_url=f"https://www.manpower.com{path}", external_job_id=raw.get("jobID"),
            description=raw.get("publicDescription"), posted_date=parse_iso(raw.get("publishfromDate")),
            employment_type_raw=raw.get("employmentType") or raw.get("jobType"),
            pay_min=raw.get("salaryRate"), pay_period=raw.get("salaryUnit"),
            department=raw.get("domain"),
        )
