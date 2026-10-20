"""
Holistic Partners - holistic-partners.com/find-a-job (own WordPress job board, JSON).

The find-a-job page reads GET https://holistic-partners.com/?cjl_api=1&page=N&per_page=50
({"total", "jobs": [...]}, newest first; Ceipal-shaped records, ~26k in the index, so a
run reads the newest pages within its time budget). Posting page:
https://holistic-partners.com/find-a-job/job-details?job_id=<id>&job_code=<code>.
Recruiter ids in the records are not stored. IT only (services.it_roles).
Verified 2026-10-20.
"""

from urllib.parse import urlencode

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import CeipalRecordsMixin, OwnSiteStaffingScraper

API_URL = "https://holistic-partners.com/"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class HolisticPartnersScraper(CeipalRecordsMixin, OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="holisticpartners",
        company_name="Holistic Partners",
        careers_url="https://holistic-partners.com/find-a-job/",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Holistic Partners"
    PER_PAGE = 50  # the endpoint's maximum
    TIME_BUDGET_SECONDS = 50

    def listing_items(self, payload):
        return self.expect_list(payload, "jobs")

    async def fetch_raw(self) -> list:
        raw, page, seen = [], 1, set()
        while len(raw) < self.MAX_JOBS:
            data = await self._http("GET", API_URL, params={
                "cjl_api": 1, "page": page, "per_page": self.PER_PAGE, "keyword": "", "location": "",
                "job_type": "", "remote": ""}, headers={"Referer": "https://holistic-partners.com/find-a-job/"})
            jobs = [j for j in self.listing_items(data) if j.get("id") not in seen]
            seen.update(j.get("id") for j in jobs)
            raw.extend(self.take_it(j for j in jobs if (j.get("job_status") or "Active") in ("Active", "Open")))
            if not jobs or len(seen) >= (data.get("total") or 0) or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        url = "https://holistic-partners.com/find-a-job/job-details?" + urlencode(
            {"job_id": raw.get("id"), "job_code": raw.get("job_code")})
        return self.ceipal_job(raw, url)
