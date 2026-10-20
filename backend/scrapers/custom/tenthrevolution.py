"""Tenth Revolution Group - www.tenthrevolution.com/jobs (own WordPress job list).

Each listing page (/jobs/, /jobs/page/N/) carries 10 div.job-description-tab blocks with
the reference, title, published date, location, brand, job type, rate and the full
description, newest first. robots.txt asks for Crawl-delay: 60, so one run reads only
the first (newest) page; detail pages answer scripts with 403 and are not needed.
Verified 2026-10-20 (~2,000 postings across Jefferson Frank / Nigel Frank / FRG brands).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, parse_when, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://www.tenthrevolution.com/jobs/"
@ScraperRegistry.register(category="custom")
class TenthRevolutionScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="tenthrevolution",
        company_name="Tenth Revolution Group",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
    )

    def listing_items(self, payload: Any) -> list:
        items = []
        for tab in soup(payload).select("div.job-description-tab"):
            a = tab.select_one("h2.job-title a[href]") or tab.find("a", href=re.compile(r"/job/[^/]+/?$"))
            if not a:
                continue
            item = {"href": abs_url(LIST_URL, a["href"]), "title": text_of(a),
                    "ref": re.sub(r"^Ref\.\s*No\.\s*", "", text_of(tab.select_one(".refrence-num")))}
            for li in tab.select(".job-description-left li"):
                key, value = li.select_one(".key"), li.select_one(".value")
                if key and value and key.name == "span":
                    item[text_of(key)] = text_of(value)
            item["Products"] = ", ".join(text_of(x) for x in tab.select("li.skill")) or None
            desc = tab.select_one(".job-description")
            item["description_html"] = str(desc) if desc else None
            items.append(item)
        return items

    async def fetch_raw(self) -> list:
        self.truncated = True  # Crawl-delay 60: the newest page only
        return self.listing_items(await self.get_text(LIST_URL))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        t = raw.get("Job Type") or None
        desc = raw.get("description_html")
        job = self.job(title=raw.get("title"), location=raw.get("Location"), job_url=raw["href"],
                       external_job_id=raw.get("ref") or raw["href"].rstrip("/").rsplit("/", 1)[-1],
                       job_description=desc, posted_date=parse_when(raw.get("Published")),
                       employment_type_raw=t,
                       employment_type="contract" if t and "contract" in t.lower() else ("full-time" if t and "perm" in t.lower() else None))
        if job:
            for key, name in (("Brand", "brand"), ("Salary/Rate", "rate_text"), ("Products", "products")):
                if raw.get(key):
                    job.extra[name] = raw[key]
        return job
