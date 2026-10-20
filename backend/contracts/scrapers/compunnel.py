"""
Compunnel - www.compunnel.com/job-search (own Staffline job API, JSON).

The job-search page posts {"PageIndex": n, "PageSize": 100, "PortalId": 5007, ...}
to https://stafflineapi.compunnel.com/job/jobsList (totalrecord ~400, newest first,
with client, bill rate, category). Each card links to the posting's Staffline page
(JobURL: staffline.compunnel.com/Support/UploadResume?JobId=...). Recruiter and sales
names in the response are not stored. IT only (JobCategory "IT" + title filter).
Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, is_us_state, join_location, parse_iso
from ._own_site import OwnSiteStaffingScraper

API_URL = "https://stafflineapi.compunnel.com/job/jobsList"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class CompunnelScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="compunnel",
        company_name="Compunnel",
        careers_url="https://www.compunnel.com/job-search/",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Compunnel"
    PAGE_SIZE = 100
    IT_TITLE_KEYS = ("Job_Title",)
    IT_CATEGORY_KEYS = ("JobCategory", "Technology_Name", "Category_Name")

    def listing_items(self, payload):
        return self.expect_list(payload, "data")

    async def fetch_raw(self) -> list:
        raw, page, seen = [], 1, 0
        while len(raw) < self.MAX_JOBS:
            body = {"PageIndex": page, "PageSize": self.PAGE_SIZE, "PortalId": 5007, "SearchKey": "",
                    "CountryId": "", "StateId": "-1", "CityId": "-1"}
            data = await self._http("POST", API_URL, json_body=body, headers={"Origin": "https://www.compunnel.com"})
            jobs = self.listing_items(data)
            seen += len(jobs)
            raw.extend(self.take_it(jobs))
            if not jobs or seen >= int(data.get("totalrecord") or 0) or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        city = raw.get("CityName") or (raw.get("Location") if raw.get("Location") not in (None, "N/A") else None)
        state = raw.get("StateName")
        location = join_location(city, state) or "United States"
        rate = raw.get("BillRate")
        return self.make_job(
            title=raw.get("Job_Title"),
            location=location,
            job_url=raw.get("JobURL"),
            external_job_id=raw.get("Job_Id"),
            description=raw.get("Job_Summary"),
            posted_date=parse_iso(raw.get("PostedOn")),
            employment_type_raw=raw.get("RequirementType") if raw.get("RequirementType") not in (None, "Other") else None,
            department=raw.get("JobCategory") or raw.get("Skill_Role_Name"),
            end_client=raw.get("Client"),
            extra={"bill_rate": rate} if rate else None,
        )
