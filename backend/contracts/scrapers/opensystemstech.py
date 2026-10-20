"""
Open Systems Technologies - www.opensystemstech.com/search (own site, server-rendered).

The search page renders a table of postings (td.job-title a -> /job/<id>/<slug>,
td.job-category, td.job-location); further pages come from the page's own
/api/requisitions/search?page=N (the same table rows as HTML). robots.txt is honoured.
IT only. Verified 2026-10-20.
"""

import re

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://www.opensystemstech.com/search"
PAGE_URL = "https://www.opensystemstech.com/api/requisitions/search"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class OpenSystemsTechScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="opensystemstech",
        company_name="Open Systems Technologies",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Open Systems Technologies"
    MAX_PAGES = 30
    IT_CATEGORY_KEYS = ("category",)

    def listing_items(self, payload):
        items = []
        for row in soup(payload).find_all("tr"):
            a = row.select_one("td.job-title a[href]")
            if not a or not re.search(r"/job/\d+/", a["href"]):
                continue
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(a),
                          "category": text_of(row.select_one("td.job-category")),
                          "location": text_of(row.select_one("td.job-location"))})
        return items

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            html = await self.get_text(LIST_URL) if page == 1 else await self.get_page_or_none(PAGE_URL, params={"page": page})
            items = [i for i in self.listing_items(html or "") if i["href"] not in seen]
            if not items:
                break
            seen.update(i["href"] for i in items)
            raw.extend(self.take_it(items))
            if self.out_of_time() or len(raw) >= self.MAX_JOBS:
                break
        return raw

    def parse_job(self, raw: dict):
        m = re.search(r"/job/(\d+)/", raw["href"])
        location = re.sub(r",\s*US$", "", raw.get("location") or "")
        return self.make_job(title=raw.get("title"), location=location, job_url=raw["href"],
                             external_job_id=m.group(1) if m else raw["href"],
                             department=raw.get("category") or None)
