"""
Akkodis (formerly Modis) - US postings.

Endpoint: ``POST https://www.akkodis.com/api/data/jobs/summarized`` - the call the
akkodis.com/en-us/careers/job-results page makes (brand "modis", country US),
sorted by PostedDate desc; 10 postings per call, ``range`` is the item offset.
Postings carry contract type ("Contractor", "Contract to Hire", "Permanent")
and min/max salary with a time scale (PERHOUR / PERYEAR).
Public posting URL: /en-us/careers/jobs/{title-location slug}/{jobId}.
Verified 2026-09-29 (~420 postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, parse_iso, slugify

API_URL = "https://www.akkodis.com/api/data/jobs/summarized"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class AkkodisScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="akkodis",
        company_name="Akkodis",
        careers_url="https://www.akkodis.com/en-us/careers/job-results",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Akkodis"

    def _payload(self, offset: int) -> dict:
        return {
            "queryString": "&sort=PostedDate desc", "baseSearchQuery": "", "filtersToDisplay": "",
            "range": offset, "siteName": "akkodis", "brand": "modis", "countryCookie": "US",
            "langCookie": "en", "brandFromDictionary": "akkodis",
        }

    async def fetch_raw(self) -> list:
        raw, offset, seen = [], 0, set()
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, json_body=self._payload(offset))
            jobs = self.expect_list(data, "jobs")
            fresh = [j for j in jobs if j.get("jobId") not in seen]
            seen.update(j.get("jobId") for j in fresh)
            raw.extend(fresh)
            pagination = data.get("pagination") or {}
            total = pagination.get("total") or 0
            nxt = pagination.get("nextRange")
            if not fresh or len(raw) >= total or self.out_of_time():
                break
            offset = nxt if isinstance(nxt, int) and nxt > offset else offset + len(jobs)
        return raw

    def parse_job(self, raw: dict):
        if raw.get("countryId") and not is_us_country(raw.get("countryId")):
            return None
        job_id = raw.get("jobId") or ""
        title = raw.get("jobTitle") or ""
        location = raw.get("jobLocation") or ""
        remote = str(raw.get("isRemote")).lower() == "true"
        return self.make_job(
            title=title,
            location=location or ("Remote" if remote else ""),
            job_url=f"https://www.akkodis.com/en-us/careers/jobs/{slugify(f'{title} {location}')}/{job_id.lower()}",
            external_job_id=job_id,
            description=raw.get("description") or raw.get("clientJobDescription"),
            posted_date=parse_iso(raw.get("postedDate") or raw.get("jobCreationDate")),
            employment_type_raw=raw.get("contractTypeTitle") or raw.get("jobType"),
            pay_min=raw.get("minsalary"),
            pay_max=raw.get("maxsalary"),
            pay_period=raw.get("salaryTimeScaleID") or raw.get("salaryTimeScale"),
            department=raw.get("jobCategoryTitle"),
            remote_type="remote" if remote else None,
            extra={"brand": raw.get("brandName"), "subcategory": raw.get("jobSubCategoryTitle")},
        )
