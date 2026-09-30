"""
Akkodis (formerly Modis) - US postings.

Endpoint: ``POST https://www.akkodis.com/api/data/jobs/summarized`` - the call the
akkodis.com/en-us/careers/job-results page makes (brand "modis", country US),
sorted by PostedDate desc; 10 postings per call, ``range`` is the item offset.
Postings carry contract type ("Contractor", "Contract to Hire", "Permanent")
and min/max salary with a time scale (PERHOUR / PERYEAR).
Public posting URL: /en-us/careers/jobs/{title-location slug}/{jobId}.
The summarized listing has no description; ``fetch_description`` reads the
schema.org JobPosting embedded in the public posting page on demand
(contracts.descriptions; robots.txt allows /en-us/careers/).
Verified 2026-09-29 (~420 postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, jsonld_job_description, parse_iso, slugify

API_URL = "https://www.akkodis.com/api/data/jobs/summarized"


def parse_akkodis_description(html: str) -> tuple:
    from contracts.descriptions import html_to_text
    fragment = jsonld_job_description(html)
    text = html_to_text(fragment)
    return (fragment, text) if text else (None, None)


def fetch_description(url: str) -> tuple:
    """On-demand description for an akkodis.com/en-us/careers/jobs/... posting URL."""
    from urllib.parse import urlparse

    from contracts.descriptions import polite_get
    u = urlparse(url or "")
    if not u.netloc.endswith("akkodis.com") or "/careers/jobs/" not in (u.path or ""):
        return None, None
    return parse_akkodis_description(polite_get(url).text)


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class AkkodisScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="akkodis",
        company_name="Akkodis",
        careers_url="https://www.akkodis.com/en-us/careers/job-results",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Akkodis"
    IT_CATEGORY_KEYS = ("jobCategoryTitle",)

    def _payload(self, offset: int) -> dict:
        return {
            "queryString": "&sort=PostedDate desc", "baseSearchQuery": "", "filtersToDisplay": "",
            "range": offset, "siteName": "akkodis", "brand": "modis", "countryCookie": "US",
            "langCookie": "en", "brandFromDictionary": "akkodis",
        }

    async def fetch_raw(self) -> list:
        raw, offset, seen, listed = [], 0, set(), 0
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, json_body=self._payload(offset))
            jobs = self.expect_list(data, "jobs")
            fresh = [j for j in jobs if j.get("jobId") not in seen]
            seen.update(j.get("jobId") for j in fresh)
            raw.extend(self.take_it(fresh))
            listed += len(fresh)
            pagination = data.get("pagination") or {}
            total = pagination.get("total") or 0
            nxt = pagination.get("nextRange")
            if not fresh or listed >= total or self.out_of_time():
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
