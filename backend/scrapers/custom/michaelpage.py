"""Michael Page (PageGroup) US - www.michaelpage.com/jobs (own Drupal job search, HTML).

Each results page (?page=N, 0-based) lists 30 li.views-row tiles: the title link
/job-detail/<slug>/ref/<jn-...>, location, contract type, salary, summary and bullet
points. Pages are read until one adds nothing new. robots.txt is honoured.
Verified 2026-10-20 (US board; other countries run their own domains).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://www.michaelpage.com/jobs"


@ScraperRegistry.register(category="custom")
class MichaelPageScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="michaelpage",
        company_name="Michael Page",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        request_timeout=45,
    )
    MAX_PAGES = 30
    TIME_BUDGET_SECONDS = 35  # each results page takes ~15 s to render

    def listing_items(self, payload: Any) -> list:
        items = []
        for row in soup(payload).select("li.views-row"):
            a = row.select_one(".job-title a[href]")
            if not a or "/job-detail/" not in a["href"]:
                continue
            summary = row.select_one(".job-summary")
            bullets = row.select_one(".bullet_points")
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(a),
                          "location": text_of(row.select_one(".job-location")),
                          "contract": text_of(row.select_one(".job-contract-type")),
                          "salary": text_of(row.select_one(".job-salary")),
                          "description_html": (str(summary) if summary else "") + (str(bullets) if bullets else "")})
        return items

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(self.MAX_PAGES):
            html = await self.get_text(LIST_URL, params={"page": page} if page else None)
            items = [i for i in self.listing_items(html) if i["href"] not in seen]
            if not items:
                break
            seen.update(i["href"] for i in items)
            raw.extend(items)
            if self.full(raw) or self.out_of_time():
                break
        else:
            self.truncated = True
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        m = re.search(r"/ref/([\w-]+)", raw["href"])
        contract = raw.get("contract") or None
        lo, hi = self.parse_salary(raw.get("salary")) if raw.get("salary") and "year" in raw["salary"].lower() else (None, None)
        job = self.job(title=raw.get("title"), location=raw.get("location"), job_url=raw["href"],
                       external_job_id=m.group(1) if m else raw["href"], job_description=raw.get("description_html") or None,
                       employment_type_raw=contract, salary_min=lo, salary_max=hi,
                       employment_type="contract" if contract and re.search(r"temp|contract|interim", contract, re.I) else (
                           "full-time" if contract and "perm" in contract.lower() else None))
        if job and raw.get("salary"):
            job.extra["salary_text"] = raw["salary"]
        return job
