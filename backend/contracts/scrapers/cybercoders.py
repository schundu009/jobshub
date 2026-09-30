"""
CyberCoders - US postings.

Endpoint: ``GET https://www.cybercoders.com/ccv5-jobs/search`` - the call the
cybercoders.com/jobs Vue app makes (query built by its SearchModel), newest
first, 100 per page. Postings carry TaxTerm ("PERM", "CONT", "CONT-TO-PERM",
...), SalaryMin/Max + SalaryType and often the hiring CompanyName, which is
kept as the end client. Recruiter names are not stored.
Public posting URL: https://www.cybercoders.com/{JobURL}.
Only the contract bucket (termOption=2) is read. Verified 2026-09-29: ~4,000
postings, of which only 4 were contract.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, US_STATES, join_location, parse_iso

API_URL = "https://www.cybercoders.com/ccv5-jobs/search"
TAX_TERMS = {
    "PERM": "Permanent",
    "CONT": "Contract",
    "CONTRACT": "Contract",
    "CONT-TO-PERM": "Contract to Hire",
    "CTH": "Contract to Hire",
    "C2H": "Contract to Hire",
}


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class CyberCodersScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="cybercoders",
        company_name="CyberCoders",
        careers_url="https://www.cybercoders.com/jobs/",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
        allow_empty=True,
    )
    AGENCY_NAME = "CyberCoders"
    PAGE_SIZE = 100
    BUSINESS_UNIT = 1  # the site's default business unit (CyberCoders)
    # The site's employment-type filter: "1" permanent, "2" contract. The board is
    # almost all direct hire (3,985 PERM vs 4 CONT on 2026-09-29), so only the
    # contract bucket is read; an empty run is normal.
    TERM_OPTION = "2"
    IT_SKILLS_KEYS = ("tags",)

    async def fetch_raw(self) -> list:
        raw, page, seen, listed = [], 1, set(), 0
        while len(raw) < self.MAX_JOBS:
            params = {"rows": str(self.PAGE_SIZE), "page": str(page), "sortType": "date",
                      "daysPosted": "0", "buid": str(self.BUSINESS_UNIT),
                      "termOption": self.TERM_OPTION}
            data = await self._http("GET", API_URL, params=params)
            jobs = self.expect_list(data, "jobs")
            fresh = [j for j in jobs if j.get("Id") not in seen]
            seen.update(j.get("Id") for j in fresh)
            raw.extend(self.take_it(fresh))
            listed += len(fresh)
            total = data.get("numFound") or 0
            if not fresh or listed >= total or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        state = _first(raw.get("StateCode"))
        city = _first(raw.get("City"))
        remote = str(raw.get("WorkLocationTypeId")) == "3"
        if state and str(state).upper() not in US_STATES:
            return None
        if not state and not remote:
            return None
        term = (raw.get("TaxTerm") or "").upper()
        salary_type = (raw.get("SalaryType") or "").lower()
        job_url = raw.get("JobURL") or ""
        return self.make_job(
            title=raw.get("jobTitle"),
            location=join_location(city, state) or "Remote",
            job_url=f"https://www.cybercoders.com/{job_url.lstrip('/')}" if job_url else None,
            external_job_id=raw.get("Id"),
            description=raw.get("ShortDescription"),
            posted_date=parse_iso(raw.get("DatePost")),
            employment_type_raw=TAX_TERMS.get(term, raw.get("TaxTerm")),
            pay_min=raw.get("SalaryMin"),
            pay_max=raw.get("SalaryMax"),
            pay_period=salary_type,
            end_client=raw.get("CompanyName"),
            remote_type={"1": "on-site", "2": "hybrid", "3": "remote"}.get(str(raw.get("WorkLocationTypeId"))),
            skills=raw.get("tags"),
        )
