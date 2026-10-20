"""
Infojini - www.infojiniconsulting.com/current-openings (own TalentDome career portal, GraphQL).

The current-openings page frames talentdome.infojiniconsulting.com/careers/<uuid>,
which posts GetPositionListForGuestUser to https://talentdome-api.infojiniconsulting.com/
(positionList with title, summary, description, location, pay, skills; totalCount ~20).
Posting page: https://talentdome.infojiniconsulting.com/careers/<uuid>/<jobPositionKey>/details.
IT only. Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import clean_location, parse_when
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import OwnSiteStaffingScraper

API_URL = "https://talentdome-api.infojiniconsulting.com/"
VENDOR = "389ff815-e886-4181-9365-f069d11a25c5"
QUERY = """query GetPositionListForGuestUser($uuid: String!, $pageId: Int, $countryCodeList: [String], $searchLocation: [LocationFilterInput], $limit: Int, $search: [String], $sortBy: Int, $jobDepartmentName: String, $jobDepartments: [Int], $status: [String], $payTypes: [Int]) {
  getPositionListForGuestUser(uuid: $uuid, filter: {pageId: $pageId, limit: $limit, sortBy: $sortBy, status: $status, search: $search, jobDepartmentName: $jobDepartmentName, jobDepartments: $jobDepartments, searchLocation: $searchLocation, payTypes: $payTypes, countryCodeList: $countryCodeList}) {
    positionList {
      jobPositionKey jobPositionId title summary description createdAt
      jobDepartment { name }
      primarySkills { name }
      location { address { cityName stateName country } }
      payDetails { payTypeId payRate { type value { minRate maxRate totalRate showPayRateOnCareerPage } } }
    }
    totalCount
  }
}"""
PAY_TYPES = {1: "hour", 2: "year", 3: "day", 4: "week", 5: "month"}


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class InfojiniScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="infojini",
        company_name="Infojini",
        careers_url="https://www.infojiniconsulting.com/current-openings",
        scraper_type=ScraperType.HTTP,
        request_timeout=40,
    )
    AGENCY_NAME = "Infojini"
    LIMIT = 50

    def it_view(self, raw):
        return {"title": raw.get("title"), "category": (raw.get("jobDepartment") or {}).get("name"),
                "skills": [s.get("name") for s in raw.get("primarySkills") or [] if s.get("name")] or None}

    def listing_items(self, payload):
        data = ((payload or {}).get("data") or {}).get("getPositionListForGuestUser") or {}
        return self.expect_list(data, "positionList")

    async def fetch_raw(self) -> list:
        raw, page, seen = [], 1, 0
        while len(raw) < self.MAX_JOBS:
            variables = {"pageId": page, "limit": self.LIMIT, "sortBy": 1, "search": [], "searchLocation": [],
                         "countryCodeList": [], "jobDepartmentName": None, "payTypes": [], "jobDepartments": [],
                         "uuid": VENDOR}
            data = await self._http("POST", API_URL, json_body={"operationName": "GetPositionListForGuestUser",
                                                                 "variables": variables, "query": QUERY},
                                    headers={"Origin": "https://talentdome.infojiniconsulting.com"})
            jobs = self.listing_items(data)
            seen += len(jobs)
            raw.extend(self.take_it(jobs))
            total = ((data.get("data") or {}).get("getPositionListForGuestUser") or {}).get("totalCount") or 0
            if not jobs or seen >= total or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        addr = ((raw.get("location") or {}).get("address")) or {}
        country = addr.get("country")
        location = clean_location(addr.get("cityName"), addr.get("stateName"), None if country == "US" else country)
        pay = raw.get("payDetails") or {}
        value = ((pay.get("payRate") or {}).get("value")) or {}
        lo = hi = period = None
        if value.get("showPayRateOnCareerPage"):
            lo, hi = value.get("minRate") or value.get("totalRate"), value.get("maxRate") or value.get("totalRate")
            period = PAY_TYPES.get(pay.get("payTypeId"))
        desc = "\n\n".join(p for p in (raw.get("summary"), raw.get("description")) if p)
        return self.make_job(
            title=raw.get("title"), location=location,
            job_url=f"https://talentdome.infojiniconsulting.com/careers/{VENDOR}/{raw.get('jobPositionKey')}/details",
            external_job_id=raw.get("jobPositionKey") or raw.get("jobPositionId"),
            description=desc or None, posted_date=parse_when(raw.get("createdAt")),
            pay_min=lo, pay_max=hi, pay_period=period,
            department=(raw.get("jobDepartment") or {}).get("name"),
            skills=[s.get("name") for s in raw.get("primarySkills") or [] if s.get("name")],
        )
