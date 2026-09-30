"""
Experis (ManpowerGroup's IT staffing brand) - US.

Endpoint: ``POST https://www.experis.com/api/services/Jobs/searchjobs`` - the call
the experis.com/en/search page makes. ``filter.offset`` is a 0-based page index
(not an item offset); 50 per page, newest first by default. Postings carry
employmentType ("Contract" / "Permanent"), a public description (HTML) and the
industry ("Technology and IT", "Engineering", ...).
The recruiter contact fields in the response are not stored.
IT only: each page is filtered per title with services.it_roles (the posting's
industry is the tie-breaker). The API also takes an industry facet filter
(``filter.industries`` = [{"key": ...}], see INDUSTRY_KEYS), but restricting to
"Technology and IT" + "Engineering" lost ~55 IT postings filed under other
industries (live check 2026-09-29: 829 vs 883 IT), and the whole board fits
the time budget, so INDUSTRIES is empty by default.
Verified 2026-09-29 (~1,470 postings).
"""

import asyncio

import aiohttp

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_state, parse_iso, parse_pay_text

API_URL = "https://www.experis.com/api/services/Jobs/searchjobs"
SITE = "https://www.experis.com"
# Industry facet keys from the searchjobs response (filters.industries).
INDUSTRY_KEYS = {
    "Technology and IT": "e39142081f614173b46a4e6c459048c5",
    "Engineering": "89fa7e6cc28e479cb5f4b7f922c37657",
}


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
    PAGE_RETRIES = 2
    RETRY_DELAY = 2.0
    INDUSTRIES: tuple = ()  # e.g. ("Technology and IT", "Engineering") to filter at the API
    IT_CATEGORY_KEYS = ("domain",)

    async def fetch_raw(self) -> list:
        raw, page, seen, listed = [], 0, set(), 0
        while len(raw) < self.MAX_JOBS:
            body = {"filter": {"offset": page, "totalCount": 0, "limit": self.PAGE_SIZE,
                               "searchkeyword": None, "haslocation": False, "language": "en"}}
            if self.INDUSTRIES:
                body["filter"]["industries"] = [{"key": INDUSTRY_KEYS[i]} for i in self.INDUSTRIES]
            data = None
            for attempt in range(self.PAGE_RETRIES + 1):
                try:
                    data = await self._http("POST", API_URL, json_body=body)
                    break
                except aiohttp.ClientResponseError as e:
                    # Deep pages sometimes answer 502 while page 0 is fine: retry,
                    # then keep what we have.
                    if not (listed and e.status >= 500):
                        raise
                    if attempt < self.PAGE_RETRIES and not self.out_of_time():
                        await asyncio.sleep(self.RETRY_DELAY)
                        continue
                    self.logger.warning(f"Experis page {page} failed ({e.status}); keeping {len(raw)} jobs")
            if data is None:
                break
            jobs = self.expect_list(data, "jobsItems")
            fresh = [j for j in jobs if j.get("jobID") not in seen]
            seen.update(j.get("jobID") for j in fresh)
            raw.extend(self.take_it(fresh))
            listed += len(fresh)
            total = ((data.get("filters") or {}).get("totalCount")) or 0
            if not fresh or listed >= total or self.out_of_time():
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
