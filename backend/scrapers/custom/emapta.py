"""Emapta Global - careers.emapta.com (own OutSystems careers app, JSON screen service).

The landing page loads its job cards with
POST https://careers.emapta.com/screenservices/Careers_UI/MainFlow/JobCards_LandingPage/DataActionGetJobs
(body {"versionInfo": {moduleVersion, apiVersion}, "screenData": {"variables": {"Limit": n}}},
newest first). The request carries OutSystems' anonymous CSRF token, the same constant
every anonymous visitor's browser sends (it is not a session or bot check); the two
version tokens are read from the app's own public files on each run, so a redeploy
does not break the scraper. Posting page: https://careers.emapta.com/JobListing?JobId=<id>.
~3,000+ postings (Philippines, Colombia, ...); a run keeps the newest MAX_JOBS.
Verified 2026-10-20.
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType, UnexpectedResponseError
from scrapers.custom._own_site import OwnSiteScraper, parse_when
from scrapers.registry import ScraperRegistry

BASE = "https://careers.emapta.com"
ACTION = "screenservices/Careers_UI/MainFlow/JobCards_LandingPage/DataActionGetJobs"
SCRIPT = f"{BASE}/scripts/Careers_UI.MainFlow.JobCards_LandingPage.mvc.js"
ANON_CSRF = "T6C+9iB49TLra4jEsMeSckDMNhQ="  # OutSystems' built-in anonymous token
COUNTRIES = {"PH": "Philippines", "CO": "Colombia", "DO": "Dominican Republic", "IN": "India",
             "MK": "North Macedonia", "LK": "Sri Lanka", "VN": "Vietnam", "MY": "Malaysia",
             "AU": "Australia", "MX": "Mexico", "ZA": "South Africa", "KE": "Kenya", "US": "United States"}


@ScraperRegistry.register(category="custom")
class EmaptaScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="emapta",
        company_name="Emapta Global",
        careers_url="https://careers.emapta.com/",
        scraper_type=ScraperType.HTTP,
        request_timeout=60,
    )

    def listing_items(self, payload: Any) -> list:
        data = self.expect_dict(self.expect_dict(payload).get("data"), "data")
        jobs = self.expect_list(self.expect_dict(data.get("Jobs"), "Jobs"), "List")
        return [j.get("JobList") or j for j in jobs]

    async def _versions(self) -> tuple[str, str]:
        module = (await self.get_json(f"{BASE}/moduleservices/moduleversioninfo")).get("versionToken")
        script = await self._http("GET", SCRIPT, expect="text", headers={"Accept": "*/*"})
        m = re.search(re.escape(ACTION) + r'"\s*,\s*"([^"]+)"', script)
        if not module or not m:
            raise UnexpectedResponseError("OutSystems version tokens not found")
        return module, m.group(1)

    async def _robots_ok(self, url: str) -> bool:
        # The app's script file is not an HTML page; robots.txt here is an OutSystems redirect.
        return True

    async def fetch_raw(self) -> list:
        module, api = await self._versions()
        body = {"versionInfo": {"moduleVersion": module, "apiVersion": api},
                "viewName": "MainFlow.Landing_Page",
                "screenData": {"variables": {"Limit": self.MAX_JOBS, "_limitInDataFetchStatus": 1}}}
        data = await self._http("POST", f"{BASE}/{ACTION}", json_body=body,
                                headers={"X-CSRFToken": ANON_CSRF, "Content-Type": "application/json; charset=UTF-8"})
        items = self.listing_items(data)
        if len(items) >= self.MAX_JOBS:
            self.truncated = True
        return items

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        site = (raw.get("Site") or "").strip()
        country = COUNTRIES.get(raw.get("CountryCode") or "", raw.get("CountryCode") or "")
        location = site.split(",")[0].strip() if site else country
        arrangement = raw.get("WorkArrangement") or ""
        if "home" in arrangement.lower() or "remote" in arrangement.lower():
            location = f"{location} (Remote)" if location else "Remote"
        return self.job(
            title=raw.get("JobTitle"),
            location=location or country,
            job_url=f"{BASE}/JobListing?JobId={raw.get('JobId')}",
            external_job_id=raw.get("JobCode") or raw.get("JobId"),
            job_description=raw.get("Description") or None,
            department=raw.get("JobFamily") or None,
            posted_date=parse_when(raw.get("PostedDateTime")),
            employment_type_raw=raw.get("Engagement") or None,
            remote_type="remote" if "home" in arrangement.lower() else ("on-site" if arrangement.lower() == "onsite" else None),
        )
