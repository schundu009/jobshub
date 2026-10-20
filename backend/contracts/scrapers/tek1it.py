"""
TekOne IT Services - www.tek1it.com/careers (own static careers page, Hyderabad).

"Open Positions": div.career-sec-job cards (h3 position, location / type / level
items, the full description, skills, an Apply button with data-jobid). The roles
have no page of their own, so job_url is the careers page with the job id as
fragment. robots.txt is honoured. IT only. Verified 2026-10-20 (4 roles).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, slugify
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://www.tek1it.com/careers"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class TekOneITScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="tek1it",
        company_name="TekOne IT Services",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    AGENCY_NAME = "TekOne IT Services"

    def listing_items(self, payload):
        items = []
        for card in soup(payload).select("div.career-sec-job"):
            title = text_of(card.select_one(".career-sec-position"))
            info = [text_of(li) for li in card.select("ul.career-sec-info li")]
            btn = card.select_one("[data-jobid]")
            skills = [text_of(li) for li in card.select("ul.career-sec-skills li")]
            desc = card
            if title:
                items.append({"title": title, "info": info, "id": btn.get("data-jobid") if btn else slugify(title),
                              "skills": skills, "description_html": str(desc)})
        return items

    async def fetch_raw(self) -> list:
        return self.take_it(self.listing_items(await self.get_text(LIST_URL)))

    def parse_job(self, raw: dict):
        info = raw.get("info") or []
        loc = info[0] if info else "Hyderabad"
        location = loc.split("/")[0].strip()
        if location and "india" not in location.lower():
            location += ", India"
        return self.make_job(title=raw["title"], location=location, job_url=f"{LIST_URL}#job-{raw['id']}",
                             external_job_id=raw["id"], description=raw.get("description_html"),
                             employment_type_raw=info[1] if len(info) > 1 else None, skills=raw.get("skills"),
                             remote_type="on-site" if "office" in loc.lower() else None)
