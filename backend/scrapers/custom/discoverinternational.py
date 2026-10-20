"""Discover International - www.discoverinternational.com/job-seekers (own site, HTML).

Server-rendered list, 6 per page (?p=1..n): a[href=/jobs/<id>/<slug>] holding the
title (p.h5), a type tag, location, date and a summary. robots.txt is honoured.
Verified 2026-10-20 (~18 openings, life-science engineering).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, parse_when, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://www.discoverinternational.com/job-seekers"


@ScraperRegistry.register(category="custom")
class DiscoverInternationalScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="discoverinternational",
        company_name="Discover International",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    MAX_PAGES = 20

    def listing_items(self, payload: Any) -> list:
        items = []
        for a in soup(payload).find_all("a", href=re.compile(r"^(https://www\.discoverinternational\.com)?/jobs/\d+/")):
            small = [text_of(p) for p in a.select("p.fs-small")]
            paras = [text_of(p) for p in a.find_all("p", class_=False)]
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(a.select_one("p.h5")),
                          "type": text_of(a.select_one("span.tag")), "location": small[0] if small else "",
                          "date": small[1] if len(small) > 1 else "", "summary": paras[-1] if paras else ""})
        return items

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            items = [i for i in self.listing_items(await self.get_text(LIST_URL, params={"p": page})) if i["href"] not in seen]
            if not items:
                break
            seen.update(i["href"] for i in items)
            raw.extend(items)
            if self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        m = re.search(r"/jobs/(\d+)/", raw["href"])
        t = raw.get("type") or None
        return self.job(title=raw.get("title"), location=raw.get("location"), job_url=raw["href"],
                        external_job_id=m.group(1) if m else raw["href"], job_description=raw.get("summary") or None,
                        posted_date=parse_when(raw.get("date")), employment_type_raw=t,
                        employment_type="contract" if t and "contract" in t.lower() else ("full-time" if t and "perm" in t.lower() else None))
