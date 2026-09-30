"""
Experis (ManpowerGroup's IT staffing brand) - US.

Endpoint: ``POST https://www.experis.com/api/services/Jobs/searchjobs`` - the call
the experis.com/en/search page makes. ``filter.offset`` is a 0-based page index
(not an item offset); 50 per page, newest first by default. Postings carry
employmentType ("Contract" / "Permanent"), a public description (HTML) and the
industry ("Technology and IT", "Engineering", ...).
The recruiter contact fields in the response are not stored.
Verified 2026-09-29 (~1,470 postings).
"""

import aiohttp

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_state, parse_iso, parse_pay_text

API_URL = "https://www.experis.com/api/services/Jobs/searchjobs"
SITE = "https://www.experis.com"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class ExperisScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="experis",
        company_name="Experis",
        careers_url="https://www.experis.com/en/search",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Experis"
    PAGE_SIZE = 50

    async def fetch_raw(self) -> list:
        raw, page, seen = [], 0, set()
        while len(raw) < self.MAX_JOBS:
            body = {"filter": {"offset": page, "totalCount": 0, "limit": self.PAGE_SIZE,
                               "searchkeyword": None, "haslocation": False, "language": "en"}}
            try:
                data = await self._http("POST", API_URL, json_body=body)
            except aiohttp.ClientResponseError as e:
                # Some deep pages answer 502 while page 0 is fine; keep what we have.
                if raw and e.status >= 500:
                    self.logger.warning(f"Experis page {page} failed ({e.status}); keeping {len(raw)} jobs")
                    break
                raise
            jobs = self.expect_list(data, "jobsItems")
            fresh = [j for j in jobs if j.get("jobID") not in seen]
            seen.update(j.get("jobID") for j in fresh)
            raw.extend(fresh)
            total = ((data.get("filters") or {}).get("totalCount")) or 0
            if not fresh or len(raw) >= total or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        location = (raw.get("jobLocation") or "").strip()
        state = location.rsplit(",", 1)[-1].strip() if "," in location else ""
        if state and not is_us_state(state):
            return None
        lo, hi, period = None, None, None
        if raw.get("salaryRate"):
            lo, hi, period = parse_pay_text(f"{raw.get('salaryRate')} {raw.get('salaryUnit') or ''}")
        url = raw.get("jobURL") or ""
        if url.startswith("/"):
            url = SITE + url
        return self.make_job(
            title=raw.get("jobTitle"),
            location=location,
            job_url=url,
            external_job_id=raw.get("jobID"),
            description=raw.get("publicDescription") or raw.get("jobAdvertisementTeaser"),
            posted_date=parse_iso(raw.get("publishfromDate")),
            employment_type_raw=raw.get("employmentType") or raw.get("jobType"),
            pay_min=lo, pay_max=hi, pay_period=period,
            department=raw.get("domain"),
            end_client=raw.get("companyName"),
        )
