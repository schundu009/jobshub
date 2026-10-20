"""
OSI Engineering - osiengineering.com/find-a-job (own WordPress job board).

The find-a-job page server-renders every opening as a.job-teaser
(/job-details/?jobid=<n>: title, field - location, and a type badge such as
Contract / Direct Hire). robots.txt is honoured. IT only. Verified 2026-10-20 (~84 openings).
"""

import re

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://osiengineering.com/find-a-job/"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class OSIEngineeringScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="osiengineering",
        company_name="OSI Engineering",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "OSI Engineering"
    IT_CATEGORY_KEYS = ("field",)

    def listing_items(self, payload):
        items, seen = [], set()
        for a in soup(payload).select("a.job-teaser[href]"):
            m = re.search(r"jobid=(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            spans = [text_of(s) for s in a.select(".full-description span")]
            items.append({"href": abs_url(LIST_URL, a["href"]), "id": m.group(1),
                          "title": text_of(a.select_one(".job-teaser__title")),
                          "field": spans[0] if spans else "", "location": spans[-1] if len(spans) > 1 else "",
                          "type": text_of(a.select_one(".badge"))})
        return items

    async def fetch_raw(self) -> list:
        return self.take_it(self.listing_items(await self.get_text(LIST_URL)))

    def parse_job(self, raw: dict):
        return self.make_job(title=raw.get("title"), location=raw.get("location"), job_url=raw["href"],
                             external_job_id=raw["id"], employment_type_raw=raw.get("type") or None,
                             department=raw.get("field") or None)
