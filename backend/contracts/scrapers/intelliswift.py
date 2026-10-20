"""
Intelliswift (an LTTS company) - www.intelliswift.com/careers/current-openings (own site, HTML).

12 div.commjoblist cards a page (h3 title, h4 location, link /current-opening/<slug>),
?page=N up to the last page link. robots.txt is honoured. The site sits behind
Akamai; if it ever answers a script with "Access Denied" the run fails (403) rather
than trying to get around it. IT only. Verified 2026-10-20 (~200 openings).
"""

import re

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://www.intelliswift.com/careers/current-openings"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class IntelliswiftScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="intelliswift",
        company_name="Intelliswift",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Intelliswift"
    MAX_PAGES = 40

    def listing_items(self, payload):
        items = []
        for card in soup(payload).select("div.commjoblist"):
            a = card.find("a", href=re.compile(r"/current-opening/"))
            if not a:
                continue
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(card.find("h3")),
                          "location": text_of(card.find("h4"))})
        return items

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            html = await self.get_page_or_none(LIST_URL, params={"page": page} if page > 1 else None)
            items = [i for i in self.listing_items(html or "") if i["href"] not in seen]
            if not items:
                break
            seen.update(i["href"] for i in items)
            raw.extend(self.take_it(items))
            if self.out_of_time() or len(raw) >= self.MAX_JOBS:
                break
        return raw

    def parse_job(self, raw: dict):
        return self.make_job(title=raw.get("title"), location=raw.get("location"), job_url=raw["href"],
                             external_job_id=raw["href"].rstrip("/").rsplit("/", 1)[-1])
