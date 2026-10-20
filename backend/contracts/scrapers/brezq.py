"""
BrezQ - brezq.com/careers (own Next.js site; schema.org JobPosting on each role page).

The careers page links each role (/careers/<slug>); every role page carries a
JobPosting JSON-LD block (title, description, datePosted, employmentType,
jobLocation, occupationalCategory), read once per role. robots.txt is honoured.
IT only. Verified 2026-10-20 (3 roles).
"""

import re

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import abs_url, jsonld_location, jsonld_postings, soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, parse_iso
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://brezq.com/careers"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class BrezQScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="brezq",
        company_name="BrezQ",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    AGENCY_NAME = "BrezQ"
    IT_AMBIGUOUS_DEFAULT = True  # an IT consultancy: "Delivery Manager" roles are technology delivery
    IT_CATEGORY_KEYS = ("occupationalCategory",)

    def listing_items(self, payload):
        hrefs = []
        for a in soup(payload).find_all("a", href=re.compile(r"^(https://brezq\.com)?/careers/[a-z0-9-]+/?$")):
            href = abs_url(LIST_URL, a["href"])
            if href not in hrefs:
                hrefs.append(href)
        return [{"href": h, "title": None} for h in hrefs]

    async def fetch_raw(self) -> list:
        raw = []
        for item in self.listing_items(await self.get_text(LIST_URL)):
            if self.out_of_time():
                break
            postings = jsonld_postings(await self.get_text(item["href"]))
            if postings:
                raw.append({**postings[0], "href": item["href"]})
        return self.take_it(raw)

    def parse_job(self, raw: dict):
        loc = raw.get("jobLocation") or {}
        location = (loc.get("name") if isinstance(loc, dict) else None) or jsonld_location(raw)
        return self.make_job(title=text_of(raw.get("title") or ""), location=location, job_url=raw.get("url") or raw["href"],
                             external_job_id=raw["href"].rstrip("/").rsplit("/", 1)[-1],
                             description=raw.get("description"), posted_date=parse_iso(raw.get("datePosted")),
                             employment_type_raw=raw.get("employmentType"),
                             department=raw.get("occupationalCategory"))
