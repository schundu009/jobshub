"""GSPANN Technologies - careers.gspann.com (own careers site, server-rendered).

/jobs-for-experienced and /jobs-for-freshers list every opening as an
a[href=/jobs/open-positions/<slug>] card: type and experience chips, h3 title,
location ("Hyderabad / Pune, IN"), "Posted 4d ago" and skill chips. robots.txt is
honoured. Verified 2026-10-20 (~120 openings).
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LISTS = ["https://careers.gspann.com/jobs-for-experienced", "https://careers.gspann.com/jobs-for-freshers"]
COUNTRY = {"IN": "India", "US": "United States", "CA": "Canada", "MX": "Mexico", "UK": "United Kingdom"}


def posted_ago(text: str) -> Optional[datetime]:
    m = re.search(r"(\d+)\s*([hdwmy])\w*\s*ago", text or "", re.I)
    if not m:
        return datetime.now(timezone.utc).replace(tzinfo=None) if re.search(r"today|just now", text or "", re.I) else None
    n, unit = int(m.group(1)), m.group(2).lower()
    days = {"h": 0, "d": n, "w": 7 * n, "m": 30 * n, "y": 365 * n}[unit]
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


@ScraperRegistry.register(category="custom")
class GSPANNScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="gspann",
        company_name="GSPANN Technologies",
        careers_url=LISTS[0],
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )

    def listing_items(self, payload: Any) -> list:
        items = []
        for a in soup(payload).select('a[href*="/jobs/open-positions/"]'):
            spans = [text_of(s) for s in a.select("h3 + div > span")]
            chips = [text_of(s) for s in a.select("span.chip")]
            items.append({"href": abs_url(LISTS[0], a["href"]), "title": text_of(a.find("h3")),
                          "location": spans[0] if spans else "", "posted": spans[1] if len(spans) > 1 else "",
                          "chips": chips})
        return items

    async def fetch_raw(self) -> list:
        raw = []
        for url in LISTS:
            raw.extend(self.listing_items(await self.get_text(url)))
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        loc = raw.get("location") or ""
        m = re.search(r",\s*([A-Z]{2})$", loc)
        if m and m.group(1) in COUNTRY:
            loc = loc[: m.start()] + ", " + COUNTRY[m.group(1)]
        chips = raw.get("chips") or []
        etype = next((c for c in chips if re.search(r"full|part|contract|intern", c, re.I)), None)
        job = self.job(title=raw.get("title"), location=loc, job_url=raw["href"],
                       external_job_id=raw["href"].rstrip("/").rsplit("/", 1)[-1],
                       posted_date=posted_ago(raw.get("posted")), employment_type_raw=etype,
                       employment_type=(etype or "").lower() or None)
        if job:
            skills = [c for c in chips if c != etype and not re.search(r"\d+\+?\s*years?", c, re.I)]
            if skills:
                job.extra["skills"] = skills[:20]
        return job
