"""PER International - www.per-international.com/jobs (semiconductor recruiter; own site, HTML).

The live-roles page lists a.jb-row links (/jobs/<slug>-<uuid>) with the title, the
(anonymised) client, location, field, contract type and salary. robots.txt is
honoured. Verified 2026-10-20 (~6 roles).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://www.per-international.com/jobs"


@ScraperRegistry.register(category="custom")
class PERInternationalScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="perinternational",
        company_name="PER International",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )

    def listing_items(self, payload: Any) -> list:
        items = []
        for a in soup(payload).select("a.jb-row[href]"):
            meta = {s.get("data-label"): text_of(s) for s in a.select(".jb-row-meta > span[data-label]")}
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(a.select_one(".jb-row-title")),
                          "client": text_of(a.select_one(".jb-row-company")), **meta})
        return items

    async def fetch_raw(self) -> list:
        return self.listing_items(await self.get_text(LIST_URL))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$", raw["href"])
        contract = raw.get("Contract") or None
        job = self.job(title=raw.get("title"), location=raw.get("Location"), job_url=raw["href"],
                       external_job_id=m.group(1) if m else raw["href"], department=raw.get("Job type") or None,
                       employment_type_raw=contract,
                       employment_type="contract" if contract and "contract" in contract.lower() else (
                           "full-time" if contract and "perm" in contract.lower() else None))
        if job:
            if raw.get("client"):
                job.extra["end_client"] = raw["client"]
            if raw.get("Salary") and "not disclosed" not in raw["Salary"].lower():
                job.extra["salary_text"] = raw["Salary"]
        return job
