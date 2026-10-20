"""
ALOIS Solutions - aloissolutions.com/opportunities/find-your-dream-job (own SPA, JSON).

The job board posts {"request": {"endpoint": "jobs", "executor": "getCeipalJobs",
"data": [<region>], ...}} to https://api.aloissolutions.com/service for each tab it
shows (APAC, UK/EU = "UK", INDIA); the records are Ceipal-shaped. Posting page:
https://aloissolutions.com/opportunities/job/<region>/<id>. IT only.
Verified 2026-10-20 (APAC 41, UK 103, INDIA ~970).
"""

from urllib.parse import quote

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY
from ._own_site import CeipalRecordsMixin, OwnSiteStaffingScraper

API_URL = "https://api.aloissolutions.com/service"
COMPANY = "67330ed87128df65b0442dz10"  # the site's own tenant id, sent by its page
REGIONS = ("APAC", "UK", "INDIA")


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class ALOISSolutionsScraper(CeipalRecordsMixin, OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="aloissolutions",
        company_name="ALOIS Solutions",
        careers_url="https://aloissolutions.com/opportunities/find-your-dream-job",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "ALOIS Solutions"

    def listing_items(self, payload):
        data = self.expect_list(payload, "data")
        rows = data[0] if data and isinstance(data[0], list) else data
        return [r for r in rows if isinstance(r, dict) and r.get("position_title")]

    async def fetch_raw(self) -> list:
        raw = []
        for region in REGIONS:
            body = {"request": {"endpoint": "jobs", "executor": "getCeipalJobs", "data": [region],
                                "metadata": {"company": {"id": COMPANY}}}}
            data = await self._http("POST", API_URL, json_body=body,
                                    headers={"Origin": "https://aloissolutions.com",
                                             "Referer": "https://aloissolutions.com/"})
            items = self.listing_items(data)
            for item in items:
                item["_region"] = region
            raw.extend(self.take_it(items))
            if self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        url = f"https://aloissolutions.com/opportunities/job/{raw['_region']}/{quote(str(raw.get('id')), safe='=')}"
        return self.ceipal_job(raw, url)
