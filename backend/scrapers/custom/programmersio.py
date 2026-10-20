"""Programmers.io - programmers.io/our-openings (own WordPress careers page).

Each opening is a div.col-box-33 card: h3.jobTitle, Experience / Salary / Location
labels and a "View Details" link https://programmers.io/job-opening-detail/?jobId=<id>.
robots.txt is honoured. Verified 2026-10-20 (16 openings, mostly India).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://programmers.io/our-openings/"


@ScraperRegistry.register(category="custom")
class ProgrammersIOScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="programmersio",
        company_name="Programmers.io",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )

    def listing_items(self, payload: Any) -> list:
        items = []
        for card in soup(payload).select("div.col-box-33"):
            a = card.find("a", href=re.compile(r"jobId=\d+"))
            if not a:
                continue
            labels = {}
            for row in card.select("div.d-flex"):
                k, v = row.select_one(".label_bx"), row.select_one(".label_desc")
                if k and v:
                    labels[text_of(k).rstrip(":").lower()] = text_of(v)
            detail = card.find("a", href=re.compile(r"job-opening-detail")) or a
            items.append({"href": abs_url(LIST_URL, detail["href"]), "title": text_of(card.select_one(".jobTitle") or a),
                          "id": re.search(r"jobId=(\d+)", a["href"]).group(1), **labels})
        return items

    async def fetch_raw(self) -> list:
        return self.listing_items(await self.get_text(LIST_URL))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        location = raw.get("location") or ""
        job = self.job(title=raw.get("title"), location=location, job_url=raw["href"], external_job_id=raw["id"])
        if job and raw.get("experience"):
            job.extra["experience"] = raw["experience"]
        return job
