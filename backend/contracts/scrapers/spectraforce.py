"""
SPECTRAFORCE - spectraforce.com/careers/professional-jobs (own Next.js site; Leoforce job API).

The professional-jobs page posts its search to
https://leoforce.us/LeoJobsAPI/api/job/GetJobsList?_OrgId=1&_UserId=1
({"TakeCount", "SkipCount", "SortBy": "ModifiedDate", ...}; TotalCount ~2,800, newest
first) - the job service the page itself calls. Posting page:
https://spectraforce.com/careers/jobs/<JobSeoTitle> (ends in the job id). IT only.
Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, parse_iso, slugify
from ._own_site import OwnSiteStaffingScraper

API_URL = "https://leoforce.us/LeoJobsAPI/api/job/GetJobsList"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class SpectraforceScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="spectraforce",
        company_name="SPECTRAFORCE",
        careers_url="https://spectraforce.com/careers/professional-jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "SPECTRAFORCE"
    TAKE = 100
    IT_TITLE_KEYS = ("JobTitle",)
    IT_CATEGORY_KEYS = ("CategoryName", "JobCategory")

    def listing_items(self, payload):
        return self.expect_list(payload, "List")

    def _body(self, skip: int) -> dict:
        return {"SearchKeyword": "", "JobIds": None, "ContractType": "", "ProjectDuration": 0, "IsRemote": -1,
                "WorkLocationTypeId": -1, "JobLocationName": "", "CountryId": 0, "StateId": 0, "LocationId": 0,
                "TakeCount": self.TAKE, "SkipCount": skip, "SortOrder": "DSC", "SortBy": "ModifiedDate",
                "OrgId": 1, "UserId": 1}

    async def fetch_raw(self) -> list:
        raw, skip = [], 0
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, params={"_OrgId": 1, "_UserId": 1}, json_body=self._body(skip),
                                    headers={"Origin": "https://spectraforce.com", "Referer": "https://spectraforce.com/"})
            jobs = self.listing_items(data)
            skip += len(jobs)
            raw.extend(self.take_it(j for j in jobs if (j.get("JobStatusName") or "Open") == "Open"))
            if not jobs or skip >= int(data.get("TotalCount") or 0) or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        seo = raw.get("JobSeoTitle") or f"{slugify(raw.get('JobTitle') or '')}-{raw.get('JobId')}"
        mode = (raw.get("WorkLocationTypeName") or "").lower()
        location = raw.get("Location") or raw.get("FullLocation")
        if (raw.get("RemoteLocation") or mode == "remote") and "remote" not in (location or "").lower():
            location = f"{location} (Remote)" if location else "Remote"
        return self.make_job(
            title=raw.get("JobTitle"),
            location=location,
            job_url=f"https://spectraforce.com/careers/jobs/{seo}",
            external_job_id=raw.get("JobId"),
            posted_date=parse_iso(raw.get("ModifiedDate")),
            employment_type_raw=" ".join(filter(None, ["Contract" if raw.get("ContractType") else None,
                                                       raw.get("ContractType")])) or None,
            pay_min=raw.get("MinimumPayRate"), pay_max=raw.get("MaximumPayRate"), pay_period=raw.get("PayRatetypeName"),
            department=raw.get("JobCategory"),
            end_client=raw.get("CompanyName"),
            remote_type={"remote": "remote", "hybrid": "hybrid", "onsite": "on-site"}.get(mode),
            extra={"duration_months": raw.get("ProjectDuration")} if raw.get("ProjectDuration") else None,
        )
