"""Science Corp - science.xyz/careers/open-positions (own static careers page).

The page server-renders every opening as li.job-list__job > a[href=/careers/<slug>-<id>]
with an h4 title and the location underneath, grouped by team (the article heading).
robots.txt is honoured. Verified 2026-10-20 (20 postings).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://science.xyz/careers/open-positions/"


@ScraperRegistry.register(category="custom")
class ScienceCorpScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="sciencecorp",
        company_name="Science Corp",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )

    def listing_items(self, payload: Any) -> list:
        items = []
        for li in soup(payload).select("li.job-list__job"):
            a = li.find("a", href=True)
            if not a or not re.search(r"/careers/[^/]+-\d+/?$", a["href"]):
                continue
            section = li.find_parent("article")
            team = text_of(section.find(["h2", "h3"])) if section else None
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(li.find(["h4", "h3"])),
                          "location": text_of(li.select_one(".job-list__description")), "team": team})
        return items

    async def fetch_raw(self) -> list:
        return self.listing_items(await self.get_text(LIST_URL))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        m = re.search(r"-(\d+)/?$", raw["href"])
        return self.job(title=raw.get("title"), location=raw.get("location"), job_url=raw["href"],
                        external_job_id=m.group(1) if m else raw["href"], department=raw.get("team") or None)
