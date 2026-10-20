"""
Innova Solutions - jobsusa.innovasolutions.com/search-jobs (own US job site, server-rendered).

10 postings a page (?page=N, ~430 in all, newest first): p.job-search__jobs-list__job-name
a -> /job/<slug>-<id> plus info rows (location, type, date). robots.txt is honoured.
India jobs live on other systems and are not read. IT only. Verified 2026-10-20.
"""

import re

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, parse_iso
from ._own_site import OwnSiteStaffingScraper

LIST_URL = "https://jobsusa.innovasolutions.com/search-jobs"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class InnovaSolutionsScraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="innovasolutions",
        company_name="Innova Solutions",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Innova Solutions"
    MAX_PAGES = 60

    def listing_items(self, payload):
        items = []
        for name in soup(payload).select("p.job-search__jobs-list__job-name"):
            a = name.find("a", href=re.compile(r"/job/"))
            if not a:
                continue
            card = name.parent
            infos = [text_of(i) for i in card.select(".job-search__jobs-list__info")] if card else []
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(a), "infos": infos})
        return items

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            html = await self.get_page_or_none(LIST_URL, params={"page": page} if page > 1 else None)
            items = [i for i in self.listing_items(html or "") if i["href"] not in seen]
            if not items:
                break
            seen.update(i["href"] for i in items)
            raw.extend(self.take_it(items))
            if self.out_of_time() or len(raw) >= self.MAX_JOBS:
                break
        return raw

    def parse_job(self, raw: dict):
        m = re.search(r"-(\d+)/?$", raw["href"])
        infos = raw.get("infos") or []
        loc = next((i for i in infos if re.search(r",\s*[A-Z]{2}\b|remote", i, re.I)), infos[0] if infos else "")
        when = next((parse_iso(i) for i in infos if parse_iso(i)), None)
        etype = next((i for i in infos if re.search(r"contract|full|perm|temp|hire", i, re.I) and i != loc), None)
        if not loc:
            mm = re.search(r"-in-([a-z-]+)-([a-z]{2})-\d+$", raw["href"])
            loc = f"{mm.group(1).replace('-', ' ').title()}, {mm.group(2).upper()}" if mm else ""
        return self.make_job(title=raw.get("title"), location=loc, job_url=raw["href"],
                             external_job_id=m.group(1) if m else raw["href"], posted_date=when,
                             employment_type_raw=etype)
