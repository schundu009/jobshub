"""Infosys - career.infosys.com (own JSON API, India job portal).

The joblist page reads one unauthenticated GET:
https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs?sourceId=1,21&searchText=ALL
(~1,700 postings with roles and requirements, ~5 MB). Posting page:
https://career.infosys.com/jobdesc?jobReferenceCode=<referenceCode>&sourceId=<sourceId>.
infosys.com/careers answers 403 to scripts and is not used. Verified 2026-10-20.
"""

from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, clean_location, parse_when
from scrapers.registry import ScraperRegistry

API_URL = "https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/getCareerSearchJobs"


@ScraperRegistry.register(category="custom")
class InfosysScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="infosys",
        company_name="Infosys",
        careers_url="https://career.infosys.com/joblist",
        scraper_type=ScraperType.HTTP,
        request_timeout=60,
    )
    MAX_JOBS = 2000

    def listing_items(self, payload: Any) -> list:
        return self.expect_list(payload)

    async def fetch_raw(self) -> list:
        data = await self.get_json(API_URL, params={"sourceId": "1,21", "searchText": "ALL"})
        items = self.listing_items(data)
        items.sort(key=lambda j: j.get("createdOn") or "", reverse=True)
        return items

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        ref = raw.get("referenceCode")
        sections = [
            ("Responsibilities", raw.get("rolesResponsibilities")),
            ("Description", raw.get("postingDescription")),
            ("Additional responsibilities", raw.get("additionalResponsibility")),
            ("Technical requirements", raw.get("technicalRequirement")),
            ("Educational requirements", raw.get("educationalRequirement")),
            ("Preferred skills", raw.get("preferredSkills")),
        ]
        desc = "\n\n".join(f"{h}:\n{v.strip()}" for h, v in sections if isinstance(v, str) and v.strip())
        lo, hi = raw.get("minExperienceLevel"), raw.get("maxExperienceLevel")
        title = raw.get("postingTitle") or raw.get("roleDesignation")
        job = self.job(
            title=title,
            location=clean_location((raw.get("location") or "").title(), raw.get("country")),
            job_url=f"https://career.infosys.com/jobdesc?jobReferenceCode={ref}&sourceId={raw.get('sourceId') or 1}",
            external_job_id=ref or raw.get("postingId"),
            job_description=desc or None,
            department=raw.get("unit") or raw.get("functionalArea"),
            posted_date=parse_when(raw.get("createdOn")),
            employment_type="full-time",
        )
        if job and lo is not None:
            job.extra["experience_years"] = f"{lo}-{hi}" if hi else str(lo)
        return job
