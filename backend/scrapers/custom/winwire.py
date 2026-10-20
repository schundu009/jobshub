"""WinWire - www.winwire.com/careers (own WordPress careers page).

The careers page renders every opening as div.apply-box (h5 title, "Location: ..."
line and an APPLY NOW link to https://www.winwire.com/jobs/<slug>/). robots.txt is
honoured. Verified 2026-10-20 (India and USA roles).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://www.winwire.com/careers/"


@ScraperRegistry.register(category="custom")
class WinWireScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="winwire",
        company_name="WinWire",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )

    def listing_items(self, payload: Any) -> list:
        items = []
        for box in soup(payload).select("div.apply-box"):
            a = box.find("a", href=re.compile(r"/jobs/[^/]+/?$"))
            if not a:
                continue
            loc = next((text_of(p) for p in box.find_all("p") if text_of(p).lower().startswith("location")), "")
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(box.find(["h5", "h4", "h3"])),
                          "location": re.sub(r"^location\s*:\s*", "", loc, flags=re.I)})
        return items

    async def fetch_raw(self) -> list:
        return self.listing_items(await self.get_text(LIST_URL))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        slug = raw["href"].rstrip("/").rsplit("/", 1)[-1]
        location = raw.get("location") or ""
        if location and not re.search(r"india|usa|united states|, [A-Z]{2}\b", location, re.I):
            location = f"{location}, India" if re.search(r"hyderabad|bangalore|bengaluru|chennai|pune", location, re.I) else location
        return self.job(title=raw.get("title"), location=location, job_url=raw["href"], external_job_id=slug)
