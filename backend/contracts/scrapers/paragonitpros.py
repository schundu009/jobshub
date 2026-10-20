"""
Paragon IT Professionals - www.paragonitpros.com/job-board (own Webflow page).

Each opening is a div.job-post (h3.job-title, an "apply" link to its own
info.paragonitpros.com page, and a rich-text description that names the city).
robots.txt is honoured. IT only. Verified 2026-10-20 (1 opening).
"""

import re

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, US_STATES
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://www.paragonitpros.com/job-board"
_CITY_RE = re.compile(r"\bin ([A-Z][a-zA-Z .'-]+, (?:%s))\b" % "|".join(US_STATES))


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class ParagonITProsScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="paragonitpros",
        company_name="Paragon IT Professionals",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    AGENCY_NAME = "Paragon IT Professionals"
    IT_AMBIGUOUS_DEFAULT = True  # an IT-only recruiter

    def listing_items(self, payload):
        items = []
        for post in soup(payload).select("div.job-post"):
            title = text_of(post.select_one(".job-title"))
            a = post.find("a", href=True)
            body = post.select_one(".w-richtext")
            if title and a:
                items.append({"title": title, "href": a["href"], "description_html": str(body) if body else None,
                              "text": text_of(body)})
        return items

    async def fetch_raw(self) -> list:
        return self.take_it(self.listing_items(await self.get_text(LIST_URL)))

    def parse_job(self, raw: dict):
        m = _CITY_RE.search(raw.get("text") or "")
        title = raw["title"]
        etype = None
        tm = re.search(r"\s+-\s+(Full Time|Contract(?: to Hire)?|Part Time|Direct Hire)$", title, re.I)
        if tm:
            etype, title = tm.group(1), title[: tm.start()]
        return self.make_job(title=title, location=m.group(1) if m else "Iowa / Minnesota / Nebraska / Arizona",
                             job_url=raw["href"], external_job_id=raw["href"].rstrip("/").rsplit("/", 1)[-1],
                             description=raw.get("description_html"), employment_type_raw=etype)
