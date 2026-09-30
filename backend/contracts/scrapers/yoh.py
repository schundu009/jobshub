"""
Yoh (Day & Zimmermann).

Endpoint: ``GET https://shazamme.io/job-results/{siteID}`` - the job feed the
jobs.yoh.com board (a Shazamme/Duda site) loads in one request; it returns every
live posting (~275) with workType ("Contract", "Contract to Hire", "Direct Hire"),
salaryFrom/To + salaryType and the full description.
Recruiter contact fields in the feed are not stored.
Verified 2026-09-29.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, join_location, parse_iso

SITE_ID = "f9dff57b-7460-422c-b06b-7141e68114c4"
FEED_URL = f"https://shazamme.io/job-results/{SITE_ID}"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class YohScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="yoh",
        company_name="Yoh",
        careers_url="https://jobs.yoh.com/",
        scraper_type=ScraperType.HTTP,
        request_timeout=60,  # one ~3 MB response
    )
    AGENCY_NAME = "Yoh"

    async def fetch_raw(self) -> list:
        data = await self._http("GET", FEED_URL)
        rows = self.expect_list(data)
        return [r.get("data") if isinstance(r, dict) and "data" in r else r for r in rows]

    def parse_job(self, raw: dict):
        if not isinstance(raw, dict):
            return None
        if raw.get("country") and not is_us_country(raw.get("country")):
            return None
        if str(raw.get("activeStatus")).lower() == "false":
            return None
        show_pay = str(raw.get("isDisplaySalary")).lower() != "false"
        return self.make_job(
            title=raw.get("jobName"),
            location=join_location(raw.get("city"), raw.get("state")),
            job_url=raw.get("jobURL"),
            external_job_id=raw.get("referenceNumber") or raw.get("jobID"),
            description=raw.get("fullDescription") or raw.get("shortDescription"),
            posted_date=parse_iso(raw.get("addedOnUTC")) or parse_iso(raw.get("postedDate")),
            employment_type_raw=raw.get("workType"),
            pay_min=raw.get("realSalaryFrom") or raw.get("salaryFrom") if show_pay else None,
            pay_max=raw.get("realSalaryTo") or raw.get("salaryTo") if show_pay else None,
            pay_period=raw.get("salaryType"),
            department=raw.get("category"),
            remote_type=(raw.get("workModel") or "").lower() or None,
            extra={"division": raw.get("siteName")},
        )
