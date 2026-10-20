"""Doghouse Recruitment - www.doghouse.nl (Amsterdam tech recruiter; own JSON API).

The find-a-job page posts {"offset":0,"size":N,"tags":[]} as text/plain to
https://www.doghouse.nl/api/jobs (metadata.count ~70). A JSON content type is
answered with 500, so the body is sent exactly as the page sends it.
Posting page: https://www.doghouse.nl/job/<slug>. Recruiter contact details in the
response are not stored. Verified 2026-10-20.
"""

import json
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, clean_location, parse_when
from scrapers.registry import ScraperRegistry

API_URL = "https://www.doghouse.nl/api/jobs"
COUNTRIES = {"NL": "Netherlands", "US": "United States", "GB": "United Kingdom", "DE": "Germany",
             "BE": "Belgium", "ES": "Spain", "PT": "Portugal", "FR": "France"}


@ScraperRegistry.register(category="custom")
class DoghouseScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="doghouse",
        company_name="Doghouse Recruitment",
        careers_url="https://www.doghouse.nl/find-a-job",
        scraper_type=ScraperType.HTTP,
    )
    PAGE = 100

    def listing_items(self, payload: Any) -> list:
        return self.expect_list(self.expect_dict(payload), "data")

    async def fetch_raw(self) -> list:
        raw, offset = [], 0
        while True:
            data = await self._http("POST", API_URL, data=json.dumps({"offset": offset, "size": self.PAGE, "tags": []}),
                                    headers={"Content-Type": "text/plain;charset=UTF-8",
                                             "Referer": "https://www.doghouse.nl/find-a-job"})
            items = self.listing_items(data)
            raw.extend(items)
            offset += len(items)
            total = (data.get("metadata") or {}).get("count") or 0
            if not items or offset >= total or self.full(raw) or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        addr = raw.get("jobAddress") or {}
        location = clean_location(addr.get("city") or addr.get("address"), addr.get("stateCode"),
                                  COUNTRIES.get(addr.get("countryCode") or "", addr.get("countryCode")))
        # Roles without an address are with Doghouse's Dutch clients (the site lists no other place).
        location = location or "Netherlands"
        parts = [raw.get("introduction") or ""]
        for block in raw.get("content") or []:
            if isinstance(block, dict):
                if block.get("heading"):
                    parts.append(f"<h3>{block['heading']}</h3>")
                parts.append(block.get("paragraph") or "")
        desc = "".join(parts).replace("\\|", "|").replace("\\[", "[").replace("\\]", "]")
        tags = [t.get("title") for t in raw.get("jobTags") or [] if isinstance(t, dict) and t.get("title")]
        job = self.job(
            title=raw.get("title"),
            location=location,
            job_url=f"https://www.doghouse.nl/job/{raw.get('slug')}",
            external_job_id=raw.get("id") or raw.get("slug"),
            job_description=desc,
            posted_date=parse_when(raw.get("_publishedAt")),
        )
        if job and tags:
            job.extra["tags"] = tags[:20]
        return job
