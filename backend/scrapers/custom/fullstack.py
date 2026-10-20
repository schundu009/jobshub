"""FullStack (FullStack Labs) - talent.fullstack.com (own JSON API).

"Browse open positions" on fullstack.com opens talent.fullstack.com/jobs, which reads
GET https://api-v1.fullstack.com/api/job-postings/public?page=N&take=30 (~2,400
postings, one per role and country, LatAm remote). Posting page:
https://talent.fullstack.com/jobs/<id>. The list has no description. Ashby board
"fullstack" is a different company. Verified 2026-10-20.
"""

import time
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, clean_location, parse_when
from scrapers.registry import ScraperRegistry

API_URL = "https://api-v1.fullstack.com/api/job-postings/public"


@ScraperRegistry.register(category="custom")
class FullStackScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="fullstacklabs",
        company_name="FullStack",
        careers_url="https://talent.fullstack.com/jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    TAKE = 30  # the API answers 400 above 30
    MIN_INTERVAL = 3.1     # x-ratelimit-limit: 20 per 60 s
    PAGES_PER_RUN = 17

    def listing_items(self, payload: Any) -> list:
        return self.expect_list(self.expect_dict(payload), "data")

    async def fetch_raw(self) -> list:
        """The API allows 20 requests a minute and 30 postings a page (~80 pages), so a run
        reads PAGES_PER_RUN pages, starting where the previous 6-hour slot stopped; the
        result is marked incomplete unless every page was read."""
        first = await self._page(1)
        raw = self.listing_items(first)
        pages = int((first.get("meta") or {}).get("pageCount") or 1)
        if pages <= self.PAGES_PER_RUN:
            order = list(range(2, pages + 1))
        else:
            self.truncated = True
            slot = int(time.time() // 21600)
            start = 2 + (slot * (self.PAGES_PER_RUN - 1)) % (pages - 1)
            order = [2 + (start - 2 + i) % (pages - 1) for i in range(self.PAGES_PER_RUN - 1)]
        for page in order:
            if self.full(raw) or self.out_of_time():
                break
            items = self.listing_items(await self._page(page))
            if not items:
                break
            raw.extend(items)
        return [i for i in raw if i.get("isPublished", True)]

    async def _page(self, page: int) -> dict:
        return await self.get_json(API_URL, params={"page": page, "take": self.TAKE, "order": "ASC",
                                                    "orderBy": "", "filter": "", "search": ""})

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        wp = (raw.get("linkedInWorkplaceType") or "").lower()
        location = clean_location(raw.get("city"), raw.get("state"), raw.get("region"))
        if wp == "remote":
            location = f"{location} (Remote)" if location else "Remote"
        etype = (raw.get("linkedInJobType") or "").replace("_", "-").lower() or None
        return self.job(
            title=raw.get("jobTitle"),
            location=location,
            job_url=f"https://talent.fullstack.com/jobs/{raw.get('id')}",
            external_job_id=raw.get("id"),
            department=raw.get("trackName") or raw.get("departmentName"),
            posted_date=parse_when(raw.get("createdAt")),
            employment_type=etype,
            employment_type_raw=raw.get("linkedInJobType"),
            remote_type={"remote": "remote", "hybrid": "hybrid", "on-site": "on-site"}.get(wp),
        )
