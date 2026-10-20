"""
Mobile Programming - www.mobileprogramming.com/careers (own ASP.NET page).

The careers page renders a GridView table (Sr. No, Position, Skill Set, Experience,
City, Country, Apply). Only the first grid page is read: further pages and Apply
are ASP.NET postbacks, which are not replayed. Postings have no page of their own,
so job_url is the careers page with the position as fragment and the id a hash of
position + city. robots.txt is honoured. IT only. Verified 2026-10-20.
"""

from urllib.parse import quote

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import clean_location, soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, slugify
from ._own_site import OwnSiteStaffingScraper, stable_id

LIST_URL = "https://www.mobileprogramming.com/careers"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class MobileProgrammingScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="mobileprogramming",
        company_name="Mobile Programming",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Mobile Programming"
    IT_SKILLS_KEYS = ("skills",)

    def listing_items(self, payload):
        items = []
        table = soup(payload).select_one("table[id*=Grid_JobDetail]")
        for tr in table.find_all("tr") if table else []:
            cells = [text_of(td) for td in tr.find_all("td", recursive=False)]
            if len(cells) >= 6 and cells[1] and cells[0].isdigit():
                items.append({"title": cells[1], "skills": cells[2], "experience": cells[3],
                              "city": cells[4], "country": cells[5]})
        return items

    async def fetch_raw(self) -> list:
        return self.take_it(self.listing_items(await self.get_text(LIST_URL)))

    def parse_job(self, raw: dict):
        location = clean_location(raw.get("city"), raw.get("country"))
        job = self.make_job(title=raw["title"], location=location,
                            job_url=f"{LIST_URL}#{quote(slugify(raw['title']))}",
                            external_job_id=stable_id(raw["title"], raw.get("city"), raw.get("country")),
                            description=f"Skills: {raw.get('skills')}\nExperience: {raw.get('experience')}",
                            skills=[s.strip() for s in (raw.get("skills") or "").split(",") if s.strip()])
        return job
